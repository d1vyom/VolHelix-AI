"""Regressions for actual commissions and tracked Spot inventory."""
import asyncio
from unittest.mock import Mock
import pytest
from backend.exchange.execution import parse_acknowledgement, submit_order
from backend.exchange.lifecycle import execute_entry, close_trade_position, reconcile_trade
from backend.exchange.schemas import OrderRequest
from backend.store.trade_log import trade_log
from backend.tests.test_execution_risk import Client
from backend.tests.test_market_lifecycle import ack
from backend.tests.test_futures_client import futures


def run(coro):
    return asyncio.run(coro)


def filled(fee='.001', asset='SOL', qty=1, status='FILLED', original=1):
    return dict(ack(status,original,qty),base_asset='SOL',
        fills=[{'qty':str(qty),'price':'100','commission':fee,'commissionAsset':asset,'tradeId':1}])


def test_spot_base_fee_is_not_resold_and_replay_cannot_reopen():
    c=Client(); c.account['balances']['SOL']={'free':.999,'total':.999,'value_usdt':99.9}
    c.get_execution_info=Mock(return_value={'status':'TRADING','base_asset':'SOL','quote_asset':'USDT',
        'filters':[{'filterType':'LOT_SIZE','minQty':'.001','stepSize':'.001'},{'filterType':'MIN_NOTIONAL','minNotional':'10'}]})
    calls=[]
    def place(**kw):
        calls.append(kw)
        return filled() if kw['side']=='BUY' else dict(ack(qty=kw['quantity'],executed=kw['quantity'],oid='13'),fills=[{'qty':str(kw['quantity']),'price':'100','commission':'.0999','commissionAsset':'USDT'}])
    c.place_order=place
    req=OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='fee-buy')
    result,t=run(execute_entry(req,client=c))
    assert result.executed_qty==1 and t.proposal.qty==.999
    closed=run(close_trade_position(t,client=c))
    assert calls[-1]['quantity']==.999 and closed.proposal.qty==0
    assert closed.entry_fees=={'SOL':.001} and closed.exit_fees=={'USDT':.0999}
    _,replay=run(execute_entry(req,client=c))
    assert replay.proposal.qty==0 and replay.closed_qty==.999
    assert replay.pnl_basis=='gross_price_difference_fees_separate'


@pytest.mark.parametrize('asset,held',[('SOL',.999),('USDT',1),('BNB',1)])
def test_actual_fee_assets_do_not_guess_conversion(asset,held):
    req=OrderRequest(symbol='SOLUSDT',qty=1)
    result=parse_acknowledgement(filled(asset=asset),req,100)
    from backend.exchange.lifecycle import persist_entry
    t=run(persist_entry(req,result))
    assert t.proposal.qty==held and t.entry_fees=={asset:.001}
    assert t.net_realized_pnl is None


def test_partial_cancel_fee_reconciliation_survives_restart_and_replay():
    c=Client(); req=OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='partial-fee')
    c.place_order=Mock(return_value=filled('.0004',qty=.4,status='PARTIALLY_FILLED'))
    _,t=run(execute_entry(req,client=c))
    assert t.proposal.qty==.3996
    c.get_order_by_client_id=Mock(return_value=filled('.0006',qty=.6,status='CANCELED'))
    t=run(reconcile_trade(run(trade_log.get_trade_by_id(t.trade_id)),client=c))
    t=run(reconcile_trade(t,client=c))
    assert t.executed_qty==.6 and t.proposal.qty==.5994 and t.entry_fees=={'SOL':.0006}


def test_order_specific_fee_recovery_failure_preserves_acknowledged_exposure():
    c=Client(); c.place_order=Mock(return_value=ack())
    c.get_order_fills=Mock(side_effect=TimeoutError())
    req=OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='fee-outage')
    result,t=run(execute_entry(req,client=c))
    assert result.executed_qty==1 and t.executed_qty==1 and t.fees_known is False
    with pytest.raises(Exception,match='fee|commission'):
        run(close_trade_position(t,client=c))
    assert run(trade_log.get_trade_by_id(t.trade_id)).proposal.qty==1
    assert c.place_order.call_count==1


def test_spot_dust_is_retained_explicitly_without_order():
    c=Client(); c.place_order=Mock(return_value=filled('.0001'))
    c.account['balances']['SOL']={'free':.9999,'total':.9999,'value_usdt':99.99}
    _,t=run(execute_entry(OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='dust'),client=c))
    # Tradeable .99 is closed; sub-step .0099 remains visible as tracked dust.
    c.place_order=Mock(return_value=dict(ack(qty=.99,executed=.99,oid='13'),fills=[{'qty':'.99','price':'100','commission':'0','commissionAsset':'USDT'}]))
    t=run(close_trade_position(t,client=c))
    assert t.proposal.qty==.0099 and t.dust_qty==.0099
    t=run(close_trade_position(t,client=c))
    assert t.proposal.qty==.0099 and t.dust_reason
    assert c.place_order.call_count==1

def test_spot_recovery_uses_only_matching_order_fills(exchange_fixture):
    sdk=exchange_fixture.trading_client
    sdk.get_my_trades.side_effect=None
    sdk.get_my_trades.return_value=[{'orderId':12,'id':1,'qty':'1','price':'100','commission':'.001','commissionAsset':'SOL'},
        {'orderId':999,'id':2,'qty':'2','price':'100','commission':'.2','commissionAsset':'SOL'}]
    assert exchange_fixture.get_order_fills('SOLUSDT','12')==[{'orderId':12,'id':1,'qty':'1','price':'100','commission':'.001','commissionAsset':'SOL'}]
    assert sdk.get_my_trades.call_args.kwargs=={'symbol':'SOLUSDT','orderId':'12','limit':1000}


def test_futures_actual_fees_do_not_reduce_signed_position(futures):
    futures.trading_client.futures_account_trades.return_value=[{'orderId':12,'id':1,'qty':'1','price':'100','commission':'.04','commissionAsset':'USDT'}]
    futures.trading_client.futures_create_order.return_value={'orderId':12,'symbol':'SOLUSDT','status':'FILLED','origQty':'1','executedQty':'1','cumQuote':'100'}
    req=OrderRequest(market='futures',symbol='SOLUSDT',side='SELL',qty=1,client_order_id='future-fee')
    _,t=run(execute_entry(req,client=futures))
    assert t.entry_fees=={'USDT':.04} and t.proposal.qty==1 and t.proposal.side=='SELL'

def test_terminal_exit_fee_outage_can_be_recovered_without_second_sell():
    c=Client(); c.account['balances']['SOL']={'free':1,'total':1,'value_usdt':100}
    c.place_order=Mock(return_value=filled('0'))
    req=OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='recover-exit')
    _,t=run(execute_entry(req,client=c))
    c.place_order=Mock(return_value=ack(oid='13'))
    c.get_order_fills=Mock(side_effect=TimeoutError())
    t=run(close_trade_position(t,client=c))
    assert t.exit_fees_known is False
    from backend.exchange.lifecycle import reconcile_intent
    exit_id=next(k for k in t.exit_executions if ':' not in k)
    c.get_order_fills=Mock(return_value=[{'qty':'1','price':'100','commission':'.1','commissionAsset':'USDT'}])
    _,t=run(reconcile_intent('spot',exit_id,client=c))
    assert t.exit_fees_known is True and t.exit_fees=={'USDT':.1}
    assert t.closed_qty==1 and c.place_order.call_count==1

def test_growing_partial_fill_with_fee_outage_marks_basis_unknown():
    from backend.exchange.lifecycle import persist_entry
    req=OrderRequest(symbol='SOLUSDT',qty=1)
    t=run(persist_entry(req,parse_acknowledgement(filled('.0004',qty=.4,status='PARTIALLY_FILLED'),req,100)))
    unknown=parse_acknowledgement(dict(ack('CANCELED',1,.6),fees_known=False),req,100)
    t=run(trade_log.update_execution(t,unknown))
    assert t.fees_known is False and t.entry_fees=={'SOL':.0004}
    assert t.proposal.qty==.5996


def test_missing_fee_fields_do_not_erase_valid_acknowledged_fill():
    raw=ack();raw['fills']=[{'qty':'1','price':'100'}]
    result=parse_acknowledgement(raw,OrderRequest(symbol='SOLUSDT',qty=1),100)
    assert result.executed_qty==1 and result.fees_known is False


def test_fee_query_recovers_gross_entry_without_selling_wallet_inventory(exchange_fixture):
    c=exchange_fixture
    sdk=c.trading_client
    sdk.create_order.side_effect=None
    sdk.create_order.return_value={'orderId':12,'symbol':'SOLUSDT','side':'BUY','type':'MARKET',
        'status':'FILLED','origQty':'1','executedQty':'1','cummulativeQuoteQty':'150'}
    sdk.get_my_trades.side_effect=None
    sdk.get_my_trades.return_value=[{'orderId':12,'id':8,'qty':'1','price':'150','commission':'.001','commissionAsset':'SOL'}]
    result,t=run(execute_entry(OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='from-history'),client=c))
    assert result.fees_known and t.proposal.qty==.999 and t.executed_qty==1

def test_partial_terminal_exit_fee_outage_blocks_residual_until_recovered():
    c=Client(); c.account['balances']['SOL']={'free':1,'total':1,'value_usdt':100}
    c.place_order=Mock(return_value=filled('0'))
    _,t=run(execute_entry(OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='partial-exit-fee'),client=c))
    c.place_order=Mock(return_value=ack('CANCELED',1,.4,100,oid='13'))
    c.get_order_fills=Mock(side_effect=TimeoutError())
    t=run(close_trade_position(t,client=c))
    from backend.exchange.execution import OrderOutcomeUnknown
    with pytest.raises(OrderOutcomeUnknown,match='commission'):
        run(close_trade_position(t,client=c))
    assert c.place_order.call_count==1 and t.proposal.qty==.6


def test_failed_signal_reads_are_unavailable_not_zero_bullish(monkeypatch):
    import backend.api.routes as routes
    from types import SimpleNamespace
    monkeypatch.setattr(routes,'_get_binance_client',lambda:SimpleNamespace(get_24hr_ticker=lambda s:{'error':'down'}))
    rows=routes.get_signals()
    assert all(row['available'] is False and row['current_price'] is None and row['trend'] is None for row in rows)

def test_repeated_unknown_fee_snapshots_preserve_already_verified_native_fees():
    from backend.exchange.lifecycle import persist_entry
    req=OrderRequest(symbol='SOLUSDT',qty=1)
    t=run(persist_entry(req,parse_acknowledgement(filled('.0004',qty=.4,status='PARTIALLY_FILLED'),req,100)))
    unknown=parse_acknowledgement(dict(ack('CANCELED',1,.6),fees_known=False),req,100)
    t=run(trade_log.update_execution(t,unknown)); t=run(trade_log.update_execution(t,unknown))
    assert t.entry_fees=={'SOL':.0004} and t.proposal.qty==.5996


def test_sub_epsilon_inventory_is_retained_as_dust_after_actual_exit():
    from backend.tests.test_market_lifecycle import record
    from backend.exchange.schemas import OrderResult
    t=record();t.proposal.qty=1.00000000001;t.executed_qty=1.00000000001
    run(trade_log.save_trade(t))
    t=run(trade_log.apply_exit(t.trade_id,OrderResult(order_id='13',client_order_id='tiny',
        exchange_status='FILLED',executed_qty=1,orig_qty=1,entry_price=100,current_price=100)))
    assert t.proposal.qty==.00000000001 and t.status.value=='OPEN'
