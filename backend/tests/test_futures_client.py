import asyncio
from unittest.mock import Mock, MagicMock
import pytest
from backend.exchange.schemas import OrderRequest
from backend.exchange.execution import preview_order, submit_order

@pytest.fixture
def futures(monkeypatch):
    from backend.exchange import futures_client as module
    from backend.config import settings
    monkeypatch.setattr(settings, 'BINANCE_FUTURES_API_KEY', 'futures-test')
    monkeypatch.setattr(settings, 'BINANCE_FUTURES_API_SECRET', 'futures-secret')
    monkeypatch.setattr(module, 'BinanceSDKClient', lambda *a,**kw: MagicMock())
    c = module.FuturesClient()
    c.trading_client.futures_get_position_mode.return_value = {'dualSidePosition':False}
    c.trading_client.futures_get_multi_assets_mode.return_value = {'multiAssetsMargin':False}
    c.trading_client.futures_symbol_config.return_value = [{'symbol':'SOLUSDT','leverage':1}]
    c.trading_client.futures_position_information.return_value = [{'symbol':'SOLUSDT','positionSide':'BOTH','positionAmt':'0','leverage':'1','markPrice':'100','notional':'0','entryPrice':'0'}]
    c.trading_client.futures_account.return_value = {'canTrade':True,'totalMarginBalance':'10000','availableBalance':'10000','assets':[{'asset':'USDT','marginBalance':'10000','availableBalance':'10000'}]}
    info = {'symbols':[{'symbol':'SOLUSDT','baseAsset':'SOL','quoteAsset':'USDT','marginAsset':'USDT','contractType':'PERPETUAL','status':'TRADING','filters':[{'filterType':'LOT_SIZE','minQty':'.01','maxQty':'10000','stepSize':'.01'},{'filterType':'MIN_NOTIONAL','notional':'10'}]}]}
    c.market_client.futures_exchange_info.return_value = info
    c.trading_client.futures_exchange_info.return_value = info
    c.market_client.futures_symbol_ticker.return_value = {'symbol':'SOLUSDT','price':'100'}
    c.market_client.futures_klines.return_value = [[1,'99','101','98','100','12',2,'1200',10,'6','600','0']]
    from backend.engine import order_flow
    monkeypatch.setattr(order_flow,'analyze_order_flow', lambda *a:None)
    monkeypatch.setattr(order_flow,'evaluate_master_strategy_setup', lambda *a:{'score':.70,'is_valid':True,'side':'SELL','levels':{'stop_loss_price':102,'take_profit_price':96}})
    return c

def request(**kw):
    return OrderRequest(market='futures',symbol='SOLUSDT',qty=1,side='SELL',**kw)

def test_futures_keys_and_endpoints_are_separate(futures,monkeypatch):
    from backend.config import settings
    assert futures.trading_client.FUTURES_TESTNET_URL == 'https://demo-fapi.binance.com/fapi'
    assert futures.market_client.testnet is False
    assert asyncio.run(preview_order(request(),client=futures))['approved']
    monkeypatch.setattr(settings,'BINANCE_FUTURES_API_KEY','')
    from backend.exchange.futures_client import FuturesClient
    c = FuturesClient()
    with pytest.raises(ValueError,match='Futures.*credentials'):
        c.get_account()

@pytest.mark.parametrize('mode,leverage',[(True,'1'),(False,'2')])
def test_unsupported_account_state_never_changes_settings(futures,mode,leverage):
    futures.trading_client.futures_get_position_mode.return_value={'dualSidePosition':mode}
    futures.trading_client.futures_symbol_config.return_value[0]['leverage']=leverage
    verdict=asyncio.run(preview_order(request(),client=futures))
    assert not verdict['approved']
    futures.trading_client.futures_create_order.assert_not_called()
    futures.trading_client.futures_change_leverage.assert_not_called()
    futures.trading_client.futures_change_position_mode.assert_not_called()

@pytest.mark.parametrize('exposure,side,qty,approved',[(2,'SELL',1,True),(-2,'BUY',1,True),(2,'BUY',1,False),(-2,'SELL',1,False),(2,'SELL',3,False),(0,'SELL',1,False)])
def test_reduce_only_uses_signed_exchange_exposure(futures,exposure,side,qty,approved):
    futures.trading_client.futures_position_information.return_value[0]['positionAmt']=str(exposure)
    r=OrderRequest(market='futures',symbol='SOLUSDT',side=side,qty=qty,reduce_only=True)
    verdict=asyncio.run(preview_order(r,client=futures))
    assert verdict['approved'] is approved

def test_public_data_and_execution_metadata_are_separate(futures,exchange_fixture):
    assert futures.get_price('SOLUSDT')['price']==100
    assert futures.get_klines('SOLUSDT')[0]['close']==100
    futures.market_client.futures_order_book.return_value={'bids':[['99','2']],'asks':[['101','3']]}
    assert futures.get_order_book('SOLUSDT')['bids']==[[99,2]]
    futures.trading_client.futures_exchange_info.return_value={'symbols':[]}
    assert not asyncio.run(preview_order(request(),client=futures))['approved']
    exchange_fixture.trading_client.get_symbol_info.side_effect=None
    exchange_fixture.trading_client.get_symbol_info.return_value=None
    assert not asyncio.run(preview_order(OrderRequest(symbol='SOLUSDT',qty=1),client=exchange_fixture))['approved']

def test_create_cancel_and_query_map_actual_futures_execution(futures):
    futures.trading_client.futures_position_information.return_value[0]['positionAmt']='2'
    raw={'orderId':42,'symbol':'SOLUSDT','status':'FILLED','origQty':'1','executedQty':'1','cumQuote':'100','avgPrice':'100'}
    futures.trading_client.futures_create_order.return_value=raw
    futures.trading_client.futures_get_order.return_value=raw
    futures.trading_client.futures_cancel_order.return_value=dict(raw,status='CANCELED')
    result=asyncio.run(submit_order(request(reduce_only=True,client_order_id='close-1'),client=futures))
    assert result.entry_price==100 and result.executed_qty==1
    assert futures.trading_client.futures_create_order.call_args.kwargs['reduceOnly']=='true'
    assert futures.get_order_by_client_id('SOLUSDT','close-1')['order_id']==42
    assert futures.cancel_order('SOLUSDT',42)['status']=='CANCELED'

@pytest.mark.parametrize('kind', ['capital','drawdown','exposure','concentration','positions','confluence','funds'])
def test_futures_entry_risk_controls_cannot_be_bypassed(futures,monkeypatch,kind):
    context=futures.get_execution_context('SOLUSDT')
    if kind=='capital': context['account']['equity']=1000
    if kind=='drawdown': context['account']['daily_pnl']=-300
    if kind=='funds': context['account']['buying_power']=50
    if kind=='confluence': context['score']=.69
    if kind in ('exposure','concentration','positions'):
        count=6 if kind=='positions' else 1
        context['account']['positions']=[{'symbol':'SOLUSDT' if kind=='concentration' else f'ASSET{i}USDT','qty':1,'market_value':6100 if kind!='positions' else 10} for i in range(count)]
    monkeypatch.setattr(futures,'get_execution_context',lambda s:context)
    assert not asyncio.run(preview_order(request(),client=futures))['approved']
    with pytest.raises(ValueError): futures.place_order(symbol='SOLUSDT',side='SELL',quantity=1)
    futures.trading_client.futures_create_order.assert_not_called()

def test_futures_preview_and_submit_routes_dispatch_market(futures,exchange_fixture,monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import fastapi_app
    from backend.exchange import registry
    import backend.api.routes as routes
    monkeypatch.setattr(registry,'_get_futures_client',lambda:futures)
    monkeypatch.setattr(routes,'_binance_client',exchange_fixture)
    futures.trading_client.futures_create_order.return_value={'orderId':81,'symbol':'SOLUSDT','status':'NEW','origQty':'1','executedQty':'0','cumQuote':'0'}
    http=TestClient(fastapi_app)
    data={'market':'futures','symbol':'SOLUSDT','qty':1,'side':'SELL'}
    verdict=http.post('/api/market/order/preview',json=data)
    assert verdict.status_code==200 and verdict.json()['market']=='futures' and verdict.json()['approved']
    result=http.post('/api/exchange/order',json=data)
    assert result.status_code==200 and result.json()['market']=='futures' and result.json()['exchange_status']=='NEW'
    exchange_fixture.trading_client.create_order.assert_not_called()
    from backend.store.trade_log import trade_log
    saved=asyncio.run(trade_log.get_trade_by_id('81'))
    assert saved.market=='futures' and saved.proposal.market=='futures'

def test_read_routes_use_market_and_report_upstream_failure(futures,monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import fastapi_app
    from backend.exchange import registry
    monkeypatch.setattr(registry,'_get_futures_client',lambda:futures)
    http=TestClient(fastapi_app)
    quote=http.get('/api/market/quote?market=futures&symbol=SOLUSDT')
    assert quote.status_code==200 and quote.json()['price']==100
    bars=http.get('/api/market/bars?market=futures&symbol=SOLUSDT&limit=10')
    assert bars.status_code==200 and bars.json()['bars'][0]['close']==100
    account=http.get('/api/market/account?market=futures')
    assert account.status_code==200 and account.json()['equity']==10000
    futures.market_client.futures_order_book.return_value={'bids':[['99','2']],'asks':[['101','3']]}
    depth=http.get('/api/market/depth?market=futures&symbol=SOLUSDT')
    assert depth.status_code==200 and depth.json()['bids']==[[99,2]]
    assert http.get('/api/market/positions?market=futures').json()['positions']==[]
    futures.market_client.futures_symbol_ticker.side_effect=RuntimeError('upstream unavailable')
    assert http.get('/api/market/quote?market=futures&symbol=SOLUSDT').status_code==503

def test_real_sdk_outbound_urls_use_production_data_and_demo_trading(monkeypatch):
    import requests
    from binance.client import Client
    from backend.exchange import futures_client as module
    from backend.config import settings
    monkeypatch.setattr(module,'BinanceSDKClient',Client)
    monkeypatch.setattr(settings,'BINANCE_FUTURES_API_KEY','test-key')
    monkeypatch.setattr(settings,'BINANCE_FUTURES_API_SECRET','test-secret')
    calls=[]
    def transport(session,method,url,**kwargs):
        calls.append((method,url))
        if 'ticker/price' in url:
            payload={'symbol':'SOLUSDT','price':'100'}
        else:
            payload={'orderId':44,'symbol':'SOLUSDT','status':'NEW','origQty':'1','executedQty':'0','cumQuote':'0'}
        response=Mock(status_code=200,text='{}')
        response.json.return_value=payload
        return response
    monkeypatch.setattr(requests.sessions.Session,'request',transport)
    c=module.FuturesClient()
    assert calls==[]  # Neither SDK constructor pings Spot.
    assert c.get_price('SOLUSDT')['price']==100
    assert c.get_order('SOLUSDT',44)['order_id']==44
    assert calls==[('GET','https://fapi.binance.com/fapi/v2/ticker/price'),('GET','https://demo-fapi.binance.com/fapi/v1/order')]

def test_futures_limits_and_unknown_outcomes(futures):
    from backend.exchange.execution import OrderOutcomeUnknown
    futures.trading_client.futures_create_order.return_value={'orderId':9,'symbol':'SOLUSDT','status':'PARTIALLY_FILLED','origQty':'1','executedQty':'.25','cumQuote':'24.75'}
    result=asyncio.run(submit_order(request(order_type='LIMIT',limit_price=99),client=futures))
    assert result.entry_price==99 and result.executed_qty==.25
    params=futures.trading_client.futures_create_order.call_args.kwargs
    assert params['price']=='99.0' and params['timeInForce']=='GTC'
    futures.trading_client.futures_create_order.side_effect=TimeoutError('lost ack')
    futures.trading_client.futures_get_order.side_effect=TimeoutError('lookup offline')
    futures.trading_client.futures_create_order.reset_mock()
    with pytest.raises(OrderOutcomeUnknown,match='reconcile client ID'):
        asyncio.run(submit_order(request(client_order_id='uncertain-1'),client=futures))
    assert futures.trading_client.futures_create_order.call_count==1
    assert futures.trading_client.futures_get_order.call_count==1

def test_futures_quote_qty_cannot_be_ignored():
    from pydantic import ValidationError
    with pytest.raises(ValidationError,match='base qty'):
        request(quote_quantity=100)

def test_futures_drawdown_identity_is_separate_from_spot(futures):
    from backend.exchange.daily_risk import observe_equity
    from backend.store.trade_log import DB_PATH
    spot=observe_equity(DB_PATH,'spot-testnet:test',10000)
    observe_equity(DB_PATH,'spot-testnet:test',9500)
    context=futures.get_execution_context('SOLUSDT')
    assert spot['daily_pnl']==0 and context['account']['daily_pnl']==0

def test_futures_closes_bypass_entry_analysis_and_funds(futures,monkeypatch):
    futures.trading_client.futures_position_information.return_value[0]['positionAmt']='-2'
    futures.trading_client.futures_account.return_value['assets'][0]['availableBalance']='0'
    monkeypatch.setattr(futures,'get_execution_context',Mock(side_effect=RuntimeError('analysis unavailable')))
    r=OrderRequest(market='futures',symbol='SOLUSDT',qty=1,side='BUY',reduce_only=True)
    assert asyncio.run(preview_order(r,client=futures))['approved']

@pytest.mark.parametrize('equity,available', [('0','0'),('-10','-20')])
def test_distressed_futures_account_can_reduce_existing_risk(futures,equity,available):
    futures.trading_client.futures_position_information.return_value[0]['positionAmt']='-2'
    futures.trading_client.futures_account.return_value['assets'][0].update(marginBalance=equity,availableBalance=available)
    close=OrderRequest(market='futures',symbol='SOLUSDT',qty=1,side='BUY',reduce_only=True)
    assert asyncio.run(preview_order(close,client=futures))['approved']
    assert not asyncio.run(preview_order(request(),client=futures))['approved']

def test_direct_futures_adapter_validates_client_order_id(futures):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        futures.place_order(symbol='SOLUSDT',side='SELL',quantity=1,client_order_id='invalid/id')
    futures.trading_client.futures_create_order.assert_not_called()

def test_futures_ticker_matches_spot_normalized_fields(futures):
    futures.market_client.futures_ticker.return_value={'symbol':'SOLUSDT','lastPrice':'100','priceChange':'2',
        'priceChangePercent':'2.04','highPrice':'101','lowPrice':'97','volume':'120','quoteVolume':'12000',
        'openPrice':'98','count':10}
    ticker=futures.get_24hr_ticker('SOLUSDT')
    assert ticker['last_price']==100 and ticker['price_change_pct']==2.04
    assert ticker['price_change']==2 and ticker['open']==98 and ticker['close']==100

@pytest.mark.parametrize('price',['NaN','0','-1'])
def test_quote_route_reports_invalid_production_price_as_unavailable(futures,monkeypatch,price):
    from fastapi.testclient import TestClient
    from backend.main import fastapi_app
    from backend.exchange import registry
    monkeypatch.setattr(registry,'_get_futures_client',lambda:futures)
    futures.market_client.futures_symbol_ticker.return_value['price']=price
    http=TestClient(fastapi_app,raise_server_exceptions=False)
    assert http.get('/api/market/quote?market=futures&symbol=SOLUSDT').status_code==503

def test_reduce_only_can_close_position_with_preexisting_higher_leverage(futures):
    futures.trading_client.futures_symbol_config.return_value[0]['leverage']=10
    futures.trading_client.futures_position_information.return_value[0]['positionAmt']='-2'
    close=OrderRequest(market='futures',symbol='SOLUSDT',qty=1,side='BUY',reduce_only=True)
    assert asyncio.run(preview_order(close,client=futures))['approved']
    assert not asyncio.run(preview_order(request(),client=futures))['approved']
