import asyncio
from unittest.mock import Mock
import pytest
from backend.exchange import execution
from backend.exchange.schemas import OrderRequest

class Client:
    def __init__(self):
        self.score = .70
        self.account = {'equity':10000,'buying_power':10000,'daily_pnl':0,'balances':{'USDT':{'free':10000,'total':10000,'value_usdt':10000}}}
        self.calls = 0
    def get_account(self): return self.account
    def get_price(self, symbol): return {'price':100}
    def get_execution_context(self, symbol):
        return {'account':self.account,'score':self.score,'is_valid':True,'side':'BUY','stop_loss':98,'take_profit':104}
    def get_exchange_info(self, symbol):
        return {'status':'TRADING','base_asset':'SOL','quote_asset':'USDT','filters':[{'filterType':'LOT_SIZE','minQty':'0.01','maxQty':'100','stepSize':'0.01'},{'filterType':'MIN_NOTIONAL','minNotional':'10'}]}
    def place_order(self, **kw):
        self.calls += 1
        return {'order_id':12,'status':'NEW','orig_qty':kw.get('quantity',1),'executed_qty':0}

def preview(c, **kwargs):
    return asyncio.run(execution.preview_order(OrderRequest(symbol='SOLUSDT',qty=1,**kwargs),client=c))

@pytest.mark.parametrize('score,approved',[(.69,False),(.70,True)])
def test_confluence_boundary(score,approved):
    c=Client(); c.score=score
    assert preview(c)['approved'] is approved

@pytest.mark.parametrize('equity,pnl,approved',[(3999,0,False),(4000,0,True),(10000,-300,False),(10000,300,True),(0,0,False)])
def test_capital_and_daily_loss_boundaries(equity,pnl,approved):
    c=Client(); c.account.update(equity=equity,daily_pnl=pnl)
    assert preview(c)['approved'] is approved

def test_spot_sell_cannot_short():
    assert not preview(Client(),side='SELL')['approved']

def test_exit_uses_exit_checks():
    c=Client(); c.account['balances']['SOL']={'free':2,'total':2,'value_usdt':200}; c.score=0;c.account['daily_pnl']=-1000
    assert preview(c,side='SELL',reduce_only=True)['approved']
    c.account['balances']['SOL']['free']=.5
    assert not preview(c,side='SELL',reduce_only=True)['approved']

def test_preview_cannot_bypass_submit_checks():
    c=Client(); assert preview(c)['approved']; c.score=.69
    with pytest.raises(execution.OrderExecutionError):
        asyncio.run(execution.submit_order(OrderRequest(symbol='SOLUSDT',qty=1),client=c))
    assert c.calls==0

def test_timeout_reconciles_client_order_id():
    c=Client(); c.place_order=Mock(side_effect=TimeoutError())
    c.get_order_by_client_id=Mock(return_value={'order_id':12,'status':'NEW','orig_qty':1,'executed_qty':0})
    result=asyncio.run(execution.submit_order(OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='test-order'),client=c))
    assert result.order_id=='12'; assert c.place_order.call_count==1
    c.get_order_by_client_id.assert_called_once_with('SOLUSDT','test-order')

def test_missing_daily_loss_is_not_zero():
    c=Client(); del c.account['daily_pnl']
    assert not preview(c)['approved']

def test_decimal_filters_reject_unaligned_quantity():
    c=Client()
    result=asyncio.run(execution.preview_order(OrderRequest(symbol='SOLUSDT',qty=1.001),client=c))
    assert not result['approved']


def test_daily_observation_survives_restart_and_deposit(tmp_path):
    from backend.exchange.daily_risk import observe_equity
    db=str(tmp_path/'risk.db')
    assert observe_equity(db,'spot:account',10000,'2026-10-20')['daily_pnl']==0
    assert observe_equity(db,'spot:account',9600,'2026-10-20')['daily_pnl']==-400
    assert observe_equity(db,'spot:account',12000,'2026-10-20')['daily_pnl']==-400
    assert observe_equity(db,'spot:account',12000,'2026-10-21')['daily_pnl']==0
    with pytest.raises(ValueError): observe_equity(db,'spot:account',0,'2026-10-21')


def test_legacy_dispatch_cannot_bypass_gate(exchange_fixture):
    exchange_fixture.get_exchange_info=Mock(return_value={'error':'unavailable'})
    with pytest.raises(ValueError):
        exchange_fixture.place_order(symbol='SOLUSDT',side='BUY',quantity=100)
    exchange_fixture.trading_client.create_order.assert_not_called()

def test_exit_does_not_need_entry_analysis():
    c=Client(); c.get_account=lambda:dict(c.account)
    c.account['balances']['SOL']={'free':2,'total':2,'value_usdt':200}
    c.get_execution_context=Mock(side_effect=RuntimeError('analysis offline'))
    assert preview(c,side='SELL',reduce_only=True)['approved']


def test_existing_gate_rejects_unknown_nav_and_accepts_profit():
    from backend.risk.risk_gate import CryptoRiskGate
    from backend.models.portfolio import PortfolioSnapshot
    from backend.models.trade import TradeProposal
    p=TradeProposal(id='risk',symbol='SOLUSDT',qty=1,entry_price=100,stop_loss=98,take_profit=104)
    assert not CryptoRiskGate().evaluate(p,PortfolioSnapshot(equity=0)).approved
    assert CryptoRiskGate().evaluate(p,PortfolioSnapshot(equity=10000,daily_pnl=400)).approved


def test_portfolio_store_marks_missing_daily_risk_unknown():
    from backend.store.portfolio_store import PortfolioStore
    from backend.models.market import Regime
    store=PortfolioStore()
    store.update_from_exchange({'equity':10000,'buying_power':10000},[],Regime.NORMAL)
    assert store.get_snapshot().daily_risk_available is False
    store.update_from_exchange({'equity':9800,'buying_power':9800,'daily_pnl':-200},[],Regime.NORMAL)
    assert store.get_snapshot().daily_pnl == -200
    assert store.get_snapshot().daily_risk_available is True

def test_server_context_values_inventory_and_records_coverage(exchange_fixture,monkeypatch):
    from backend.mcp.client import BinanceClient
    from backend.engine import order_flow
    c=exchange_fixture
    c.trading_client.get_account.return_value={'canTrade':True,'balances':[{'asset':'USDT','free':'10000','locked':'0'},{'asset':'SOL','free':'2','locked':'0'}]}
    monkeypatch.setattr(c,'get_klines',lambda *a,**kw:[{'close':150}])
    monkeypatch.setattr(order_flow,'analyze_order_flow',lambda *a:None)
    monkeypatch.setattr(order_flow,'evaluate_master_strategy_setup',lambda *a:{'score':.70,'is_valid':True,'side':'BUY','levels':{'stop_loss_price':140,'take_profit_price':170}})
    context=BinanceClient.get_execution_context(c,'SOLUSDT')
    assert context['account']['equity']==10300
    assert context['account']['daily_pnl']==0
    assert context['account']['coverage_started_at']


def test_deposit_cannot_clear_observed_drawdown_breaker():
    c=Client(); c.account.update(equity=20000,baseline_equity=10000,daily_pnl=-300)
    assert not preview(c)['approved']

def test_bot_and_executor_cannot_bypass_fresh_gate(exchange_fixture,monkeypatch):
    import backend.api.routes as routes
    from backend.main import fastapi_app
    from fastapi.testclient import TestClient
    from backend.agents.executor import ExecutionAgent
    from backend.models.trade import TradeProposal
    from backend.models.risk import RiskGateResult
    monkeypatch.setattr(exchange_fixture,'get_execution_context',lambda symbol:{'account':{'equity':10000,'daily_pnl':0},'score':.69})
    monkeypatch.setattr(routes,'_binance_client',exchange_fixture)
    response=TestClient(fastapi_app).post('/api/bot/execute-trade',json={'symbol':'SOLUSDT'})
    assert response.status_code>=400
    record=ExecutionAgent(exchange_fixture).execute(TradeProposal(id='bypass',symbol='SOLUSDT',qty=1),RiskGateResult(approved=True,reason='client approval',timestamp='2026-10-21'))
    assert record.status.value=='CANCELLED'
    exchange_fixture.trading_client.create_order.assert_not_called()


def test_preview_endpoint_is_registered_and_returns_server_verdict(exchange_fixture,monkeypatch):
    from backend.main import fastapi_app
    from fastapi.testclient import TestClient
    import backend.api.routes as routes
    monkeypatch.setattr(routes,'_binance_client',exchange_fixture)
    response=TestClient(fastapi_app).post('/api/market/order/preview',json={'symbol':'SOLUSDT','qty':.5,'approved':True})
    assert response.status_code==200
    assert response.json()['approved'] is True
    assert response.json()['market']=='spot'
    assert 'coverage_started_at' in response.json()
    exchange_fixture.trading_client.create_order.assert_not_called()


def test_auto_trader_scan_approval_cannot_bypass_fresh_gate(exchange_fixture,monkeypatch):
    from types import SimpleNamespace
    import backend.engine.auto_trader as module
    # Import module explicitly because package exports can alias the singleton.
    import importlib
    module=importlib.import_module('backend.engine.auto_trader')
    c=exchange_fixture
    monkeypatch.setattr(c,'get_execution_context',lambda symbol:{'account':{'equity':10000,'daily_pnl':0},'score':.69})
    monkeypatch.setattr(c,'get_klines',lambda *a,**kw:[{'close':150}])
    monkeypatch.setattr(module,'analyze_order_flow',lambda *a:SimpleNamespace(current_price=150))
    monkeypatch.setattr(module,'evaluate_master_strategy_setup',lambda **kw:{'is_valid':True,'score':.9,'levels':{'take_profit_price':170,'stop_loss_price':140}})
    monkeypatch.setattr(module.auto_trader,'_get_binance_client',lambda:c)
    with pytest.raises(ValueError): module.auto_trader.trigger_cycle('SOLUSDT')
    c.trading_client.create_order.assert_not_called()


def test_market_supplied_price_cannot_understate_adapter_capital(exchange_fixture):
    exchange_fixture.trading_client.create_order.side_effect = None
    exchange_fixture.trading_client.create_order.return_value = {'orderId':42,'symbol':'SOLUSDT','side':'BUY','type':'MARKET','status':'NEW','origQty':'100','executedQty':'0'}
    with pytest.raises(ValueError, match='capital_limit'):
        exchange_fixture.place_order(symbol='SOLUSDT',side='BUY',quantity=100,order_type='MARKET',price=1)
    exchange_fixture.trading_client.create_order.assert_not_called()

def test_market_preview_uses_market_price_even_with_limit_field(exchange_fixture,monkeypatch):
    from backend.main import fastapi_app
    from fastapi.testclient import TestClient
    import backend.api.routes as routes
    monkeypatch.setattr(routes,'_binance_client',exchange_fixture)
    response=TestClient(fastapi_app).post('/api/market/order/preview',json={'symbol':'SOLUSDT','qty':100,'order_type':'MARKET','limit_price':1})
    data=response.json()
    assert data['approved'] is False
    assert float(data['price'])==150
    assert float(data['notional'])==15000
    exchange_fixture.trading_client.create_order.assert_not_called()

def test_limit_http_preview_price_matches_quantity_and_notional(exchange_fixture,monkeypatch):
    from decimal import Decimal
    from backend.main import fastapi_app
    from fastapi.testclient import TestClient
    import backend.api.routes as routes
    monkeypatch.setattr(routes,'_binance_client',exchange_fixture)
    response=TestClient(fastapi_app).post('/api/market/order/preview',json={'symbol':'SOLUSDT','qty':1,'order_type':'LIMIT','limit_price':90})
    assert response.status_code==200
    data=response.json()
    assert data['approved'] is True
    assert Decimal(data['price'])==90
    assert Decimal(data['price'])*Decimal(data['quantity'])==Decimal(data['notional'])
    exchange_fixture.trading_client.create_order.assert_not_called()
