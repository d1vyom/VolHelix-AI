"""Cross-contract scanner/dispatch regressions; real strategy and risk gate."""
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from backend.config import settings
from backend.engine import order_flow
from backend.engine.auto_trader import auto_trader
from backend.marketdata.hub import get_hub
from backend.mcp.client import BinanceClient
from backend.exchange.execution import validate_order
from backend.exchange.schemas import OrderRequest

def analysis():
    return order_flow.OrderFlowAnalysis(symbol='SOLUSDT',timestamp='fixture',current_price=100,trend_bias='BULLISH',
        nearest_bullish_ob=order_flow.OrderBlock(id='ob',block_type='BULLISH',low=98,high=100,mean_threshold=99,volume=100,timestamp='fixture',strength=1),
        unfilled_fvgs=[order_flow.FairValueGap(id='fvg',gap_type='BEARISH',top=105,bottom=104,midpoint=104.5,size=1,timestamp='fixture')])

def configure(monkeypatch,client,states,enabled=True):
    monkeypatch.setattr(settings,'FLOW_CONFLUENCE_ENABLED',enabled)
    monkeypatch.setattr(client,'get_execution_context',BinanceClient.get_execution_context.__get__(client))
    monkeypatch.setattr(client,'get_klines',lambda *a,**k:[{'close':100}]*25)
    monkeypatch.setattr(client,'get_price',lambda *a,**k:{'price':100})
    monkeypatch.setattr(order_flow,'analyze_order_flow',lambda *a,**k:analysis())
    monkeypatch.setattr('backend.engine.auto_trader.analyze_order_flow',lambda *a,**k:analysis())
    monkeypatch.setattr(auto_trader,'_get_binance_client',lambda:client)
    def metrics(_):
        state=states.pop(0) if len(states)>1 else states[0]
        if state is None:return None
        return SimpleNamespace(health=SimpleNamespace(status=state,gap_events=0),cvd_divergence=None,spread_bps=1,cvd_slope=1,session_cvd=10,stacked_imbalance_bias='BUY',absorption_flag='SELL_ABSORBED',book_imbalance=.2,price_vs_value='IN_VALUE',price=100,val=98,vah=105)
    monkeypatch.setattr(get_hub('spot'),'get_metrics',metrics)
    monkeypatch.setattr(get_hub('spot'),'get_footprint_bars',lambda *a,**k:[1]*20)
    dispatch=Mock(return_value={'order_id':'flow-entry','status':'FILLED','orig_qty':2,'executed_qty':2,'cummulative_quote_qty':200,'base_asset':'SOL','fees_known':True})
    monkeypatch.setattr(client,'place_order',dispatch)
    return dispatch

@pytest.mark.parametrize('state',[None,'WARMING_UP','STALE','DISCONNECTED','LIVE'])
def test_actual_scan_uses_shared_hub(monkeypatch,exchange_fixture,state):
    dispatch=configure(monkeypatch,exchange_fixture,[state])
    result=auto_trader._execute_scan_cycle('SOLUSDT')
    assert result['executed'] is (state=='LIVE')
    assert dispatch.call_count==(1 if state=='LIVE' else 0)
    if state=='LIVE':
        assert dispatch.call_args.kwargs['quote_quantity']==200
        assert result['score']>=.70
    else:assert result['scanner_diagnostics']['SOLUSDT']['status_label']=='FLOW VETO'

def test_scan_live_then_dispatch_stale_fails_closed(monkeypatch,exchange_fixture):
    dispatch=configure(monkeypatch,exchange_fixture,['LIVE','STALE'])
    result=auto_trader._execute_scan_cycle('SOLUSDT')
    assert result['executed'] is False
    assert dispatch.call_count==0

def test_disabled_flow_preserves_bar_strategy_and_sizing(monkeypatch,exchange_fixture):
    dispatch=configure(monkeypatch,exchange_fixture,[None],enabled=False)
    result=auto_trader._execute_scan_cycle('SOLUSDT')
    bar_only=order_flow.evaluate_master_strategy_setup('SOLUSDT',100,analysis(),tick_size='.01')
    assert result['executed'] and result['score']==bar_only['score']==.90
    assert dispatch.call_args.kwargs['quote_quantity']==200

def test_absent_flow_does_not_block_exit(monkeypatch,exchange_fixture):
    configure(monkeypatch,exchange_fixture,[None])
    exchange_fixture.trading_client.get_account.return_value['balances'].append({'asset':'SOL','free':'1','locked':'0'})
    assert validate_order(OrderRequest(symbol='SOLUSDT',side='SELL',qty=1,reduce_only=True),client=exchange_fixture)['approved']


@pytest.mark.parametrize('enabled',[False,True])
def test_flow_read_failure_is_shadow_only_when_disabled(monkeypatch,exchange_fixture,enabled):
    dispatch=configure(monkeypatch,exchange_fixture,['LIVE'],enabled=enabled)
    monkeypatch.setattr(get_hub('spot'),'get_metrics',Mock(side_effect=RuntimeError('Flow warming')))
    result=auto_trader._execute_scan_cycle('SOLUSDT')
    assert result['executed'] is (not enabled)
    assert dispatch.call_count==(0 if enabled else 1)
    if enabled:assert result['scanner_diagnostics']['SOLUSDT']['status_label']=='FLOW VETO'
