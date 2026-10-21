import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from backend.main import fastapi_app
from backend.exchange.schemas import OrderRequest
from backend.exchange.execution import submit_order, OrderExecutionError
from backend.models.trade import TradeRecord, TradeProposal
from backend.models.market import TradeStatus
from backend.store.trade_log import trade_log
from backend.tests.test_execution_risk import Client
from backend.tests.test_futures_client import futures

api = TestClient(fastapi_app)


def run(awaitable):
    return asyncio.run(awaitable)


def ack(status='FILLED', qty=1, executed=1, price=100, oid='12'):
    return dict(order_id=oid,status=status,orig_qty=qty,executed_qty=executed,
                cummulative_quote_qty=executed*price)


def record(market='spot', oid='12', qty=1, side='BUY'):
    return TradeRecord(trade_id=f'{market}:SOLUSDT:{oid}',market=market,
        proposal=TradeProposal(id=oid,market=market,symbol='SOLUSDT',side=side,qty=qty,entry_price=100),
        entry_price=100,executed_qty=qty,requested_qty=qty,binance_order_id=oid,exchange_status='FILLED',
        take_profit_price=104,stop_loss_price=98)


def test_legacy_trade_defaults_to_spot():
    trade = TradeRecord.model_validate({'trade_id':'old','proposal':{'id':'old','symbol':'SOLUSDT'}})
    assert trade.market == trade.proposal.market == 'spot'


def test_same_symbol_positions_are_market_isolated():
    run(trade_log.save_trade(record()))
    run(trade_log.save_trade(record('futures')))
    result = api.get('/api/positions?market=futures').json()
    assert len(result)==1 and result[0]['market']=='futures'


def test_stable_id_reuses_ack_and_conflicting_payload_never_dispatches():
    c=Client(); request=OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='stable')
    run(submit_order(request,client=c))
    run(submit_order(request,client=c))
    assert c.calls==1
    with pytest.raises(OrderExecutionError,match='conflict'):
        run(submit_order(request.model_copy(update={'qty':2}),client=c))
    assert c.calls==1


def test_unknown_retry_reconciles_without_resubmitting():
    c=Client(); c.place_order=Mock(side_effect=TimeoutError())
    c.get_order_by_client_id=Mock(side_effect=TimeoutError())
    request=OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='unknown')
    with pytest.raises(OrderExecutionError): run(submit_order(request,client=c))
    c.get_order_by_client_id=Mock(return_value=ack())
    result=run(submit_order(request,client=c))
    assert result.executed_qty==1
    assert c.place_order.call_count==1


def test_durable_pending_reservations_enforce_funds_across_restarts():
    c=Client(); c.account['buying_power']=150
    run(submit_order(OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='first'),client=c))
    other=Client(); other.account['buying_power']=150
    with pytest.raises(OrderExecutionError,match='reserv'):
        run(submit_order(OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='second'),client=other))
    assert other.calls==0


def test_cancel_partial_retains_exposure_and_weighted_actual_price():
    from backend.exchange.lifecycle import cancel_trade_order
    t=record(); t.status=TradeStatus.PENDING; t.exchange_status='NEW'; t.executed_qty=0; t.proposal.qty=0
    run(trade_log.save_trade(t))
    c=Client(); c.cancel_order=Mock(return_value=ack('CANCELED',1,.4,105))
    c.get_order=Mock(return_value=ack('CANCELED',1,.4,105))
    result=run(cancel_trade_order(t,client=c))
    assert result.status==TradeStatus.OPEN
    assert result.proposal.qty==.4 and result.entry_price==105
    assert result.exchange_status=='CANCELED'


def test_futures_exit_is_reduce_only_and_signed():
    from backend.exchange.lifecycle import close_trade_position
    t=record('futures',side='SELL'); run(trade_log.save_trade(t))
    c=Client(); c.market='futures'
    c.get_execution_info=Mock(return_value={'status':'TRADING','quote_asset':'USDT','contract_type':'PERPETUAL','margin_asset':'USDT','filters':[{'filterType':'LOT_SIZE','minQty':'.01','stepSize':'.01'}]})
    c.account.update(can_trade=True,positions=[{'symbol':'SOLUSDT','qty':-1,'market_value':100}])
    c.place_order=Mock(return_value=ack(price=90))
    result=run(close_trade_position(t,client=c))
    assert result.status==TradeStatus.CLOSED and result.realized_pnl==10
    assert c.place_order.call_args.kwargs['reduce_only'] is True
    assert c.place_order.call_args.kwargs['side']=='BUY'


def test_unacknowledged_exit_keeps_position_open():
    from backend.exchange.lifecycle import close_trade_position
    t=record(); run(trade_log.save_trade(t))
    c=Client(); c.account['balances']['SOL']={'free':1,'total':1,'value_usdt':100}
    c.place_order=Mock(side_effect=TimeoutError()); c.get_order_by_client_id=Mock(side_effect=TimeoutError())
    with pytest.raises(OrderExecutionError): run(close_trade_position(t,client=c))
    assert run(trade_log.get_trade_by_id(t.trade_id)).status==TradeStatus.OPEN


def test_partial_exit_only_realizes_confirmed_quantity_once():
    from backend.exchange.lifecycle import close_trade_position
    t=record(); run(trade_log.save_trade(t))
    c=Client(); c.account['balances']['SOL']={'free':1,'total':1,'value_usdt':100}
    c.place_order=Mock(return_value=ack('PARTIALLY_FILLED',1,.4,110))
    c.get_order_by_client_id=Mock(return_value=ack('PARTIALLY_FILLED',1,.4,110))
    first=run(close_trade_position(t,client=c))
    second=run(close_trade_position(first,client=c))
    assert second.proposal.qty==.6 and second.realized_pnl==4
    assert second.status==TradeStatus.OPEN
    assert c.place_order.call_count==1


def test_guardian_outage_does_not_close_or_block_other_market(monkeypatch):
    import backend.engine.auto_trader as module
    import backend.exchange.registry as registry
    spot=record(); futures=record('futures',side='SELL')
    run(trade_log.save_trade(spot)); run(trade_log.save_trade(futures))
    bad=Client(); bad.get_price=Mock(side_effect=TimeoutError())
    good=Client(); good.get_price=Mock(return_value={'price':95})
    monkeypatch.setattr(registry,'get_exchange_client',lambda market:bad if market=='spot' else good)
    calls=[]
    monkeypatch.setattr(module.auto_trader,'_close_position_and_finalize_trade',lambda **kw:calls.append(kw))
    module.auto_trader._check_and_manage_positions()
    assert len(calls)==1 and calls[0]['trade'].market=='futures'
    assert len(run(trade_log.get_open_trades()))==2


def test_unknown_intent_visible_after_restart(monkeypatch):
    import backend.exchange.registry as registry
    c=Client(); c.place_order=Mock(side_effect=TimeoutError())
    c.get_order_by_client_id=Mock(side_effect=TimeoutError())
    monkeypatch.setattr(registry,'get_exchange_client',lambda market:c)
    with pytest.raises(OrderExecutionError):
        run(submit_order(OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='visible'),client=c))
    result=api.get('/api/exchange/orders?market=spot').json()
    assert any(row.get('client_order_id')=='visible' and row.get('status')=='UNKNOWN' for row in result)


def test_positions_outage_preserves_stored_market_exposure(monkeypatch):
    import backend.exchange.registry as registry
    run(trade_log.save_trade(record('futures')))
    c=Client(); c.get_positions=Mock(side_effect=TimeoutError())
    monkeypatch.setattr(registry,'get_exchange_client',lambda market:c)
    response=api.get('/api/market/positions?market=futures')
    assert response.status_code==200
    data=response.json()
    assert data['available'] is False and data['positions'][0]['qty']==1
    assert data['positions'][0]['market']=='futures'


def test_concurrent_same_id_dispatches_once():
    c=Client(); request=OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='concurrent')
    def submit():
        try: return run(submit_order(request,client=c))
        except OrderExecutionError: return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda _:submit(),range(2)))
    assert c.calls==1 and any(results)


def test_concurrent_different_ids_cannot_overreserve():
    c=Client(); c.account['buying_power']=150
    def submit(i):
        try: return run(submit_order(OrderRequest(symbol='SOLUSDT',qty=1,client_order_id=f'parallel{i}'),client=c))
        except OrderExecutionError: return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(submit,range(2)))
    assert sum(result is not None for result in results)==1 and c.calls==1


def test_api_entry_and_repeated_close_are_market_isolated(monkeypatch,futures):
    import backend.exchange.registry as registry
    import backend.api.routes as routes
    run(trade_log.save_trade(record('spot')))
    t=record('futures',side='SELL'); run(trade_log.save_trade(t))
    futures.trading_client.futures_position_information.return_value=[{'symbol':'SOLUSDT','positionSide':'BOTH','positionAmt':'-1','leverage':'1','markPrice':'100','notional':'-100','entryPrice':'100'}]
    futures.trading_client.futures_create_order.return_value={'orderId':21,'symbol':'SOLUSDT','status':'FILLED','origQty':'1','executedQty':'1','cumQuote':'90'}
    monkeypatch.setattr(routes,'get_exchange_client',lambda market:futures)
    response=api.post('/api/exchange/close-position',json={'market':'futures','symbol':'SOLUSDT','trade_id':t.trade_id})
    assert response.status_code==200 and response.json()['status']=='CLOSED'
    assert run(trade_log.get_trade_by_id('spot:SOLUSDT:12')).status==TradeStatus.OPEN


def test_simulated_fill_endpoint_rejected_without_exchange_dispatch():
    t=record(); t.status=TradeStatus.PENDING; run(trade_log.save_trade(t))
    result=api.post(f'/api/trades/{t.trade_id}/fill',json={'fill_price':99})
    assert result.status_code==400
    assert run(trade_log.get_trade_by_id(t.trade_id)).status==TradeStatus.PENDING


def test_partial_exit_reconciliation_survives_finished_intent_before_trade_update():
    from backend.exchange.lifecycle import close_trade_position
    from backend.store import order_intents
    t=record(); run(trade_log.save_trade(t))
    c=Client(); c.account['balances']['SOL']={'free':1,'total':1,'value_usdt':100}
    c.place_order=Mock(return_value=ack('PARTIALLY_FILLED',1,.4,110))
    t=run(close_trade_position(t,client=c))
    intent=order_intents.pending()[0]
    req=OrderRequest.model_validate_json(intent['payload'])
    from backend.exchange.execution import parse_acknowledgement
    order_intents.finish(req,parse_acknowledgement(ack('FILLED',1,1,115),req,115))
    updated=run(close_trade_position(t,client=c))
    assert updated.status==TradeStatus.CLOSED and updated.realized_pnl==15
    assert c.place_order.call_count==1


def test_entry_retry_does_not_reopen_closed_position():
    from backend.exchange.lifecycle import execute_entry, close_trade_position
    c=Client(); c.account['balances']['SOL']={'free':1,'total':1,'value_usdt':100}
    c.place_order=Mock(return_value=ack())
    req=OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='reopen')
    _,t=run(execute_entry(req,client=c)); run(close_trade_position(t,client=c))
    _,retried=run(execute_entry(req,client=c))
    assert retried.status==TradeStatus.CLOSED and retried.proposal.qty==0


def test_cancel_requires_confirmed_terminal_state():
    from backend.exchange.lifecycle import cancel_trade_order
    t=record(); t.status=TradeStatus.PENDING; t.exchange_status='NEW'; t.executed_qty=0; t.proposal.qty=0
    run(trade_log.save_trade(t))
    c=Client(); c.cancel_order=Mock(return_value={'status':'CANCELED'})
    c.get_order=Mock(return_value=ack('NEW',1,0))
    with pytest.raises(OrderExecutionError): run(cancel_trade_order(t,client=c))


def test_direct_store_cannot_invent_fill_or_close():
    t=record(); run(trade_log.save_trade(t))
    with pytest.raises(ValueError,match='exchange'):
        run(trade_log.fill_pending_trade(t.trade_id,100))
    with pytest.raises(ValueError,match='exchange'):
        run(trade_log.close_trade(t.trade_id,100))


def test_persisted_small_price_and_short_protection_remains_directional():
    from backend.exchange.lifecycle import persist_entry
    from backend.exchange.schemas import OrderResult
    for market,side in [('spot','BUY'),('futures','SELL')]:
        req=OrderRequest(market=market,symbol='TINYUSDT',qty=100,side=side)
        result=OrderResult(order_id='tiny',exchange_status='FILLED',executed_qty=100,orig_qty=100,
                           entry_price=.000000001,current_price=.000000001)
        t=run(persist_entry(req,result))
        if side=='BUY': assert 0<t.stop_loss_price<t.entry_price<t.take_profit_price
        else: assert 0<t.take_profit_price<t.entry_price<t.stop_loss_price


def test_configured_account_change_cannot_replay_ack(monkeypatch):
    from backend.config import settings
    c=Client(); req=OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='account-bound')
    run(submit_order(req,client=c))
    monkeypatch.setattr(settings,'BINANCE_API_KEY','different-account')
    with pytest.raises(OrderExecutionError,match='account identity'):
        run(submit_order(req,client=c))
    assert c.calls==1


def test_guardian_recovers_unknown_entry_without_creating_again(monkeypatch):
    import backend.engine.auto_trader as module
    import backend.exchange.registry as registry
    c=Client(); c.place_order=Mock(side_effect=TimeoutError())
    c.get_order_by_client_id=Mock(side_effect=TimeoutError())
    request=OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='recover')
    with pytest.raises(OrderExecutionError): run(submit_order(request,client=c))
    c.get_order_by_client_id=Mock(return_value=ack(price=100))
    monkeypatch.setattr(registry,'get_exchange_client',lambda market:c)
    module.auto_trader._check_and_manage_positions()
    trades=run(trade_log.get_open_trades())
    assert len(trades)==1 and trades[0].entry_price==100 and trades[0].proposal.qty==1
    assert c.place_order.call_count==1


def test_stale_ack_cannot_regress_durable_execution():
    from backend.store import order_intents
    from backend.exchange.execution import parse_acknowledgement
    c=Client(); req=OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='monotonic')
    run(submit_order(req,client=c))
    order_intents.finish(req,parse_acknowledgement(ack(),req,100))
    order_intents.finish(req,parse_acknowledgement(ack('NEW',1,0),req,100))
    assert order_intents.get(req)['status']=='FILLED'


def test_account_position_limit_counts_unfilled_orders(monkeypatch):
    from backend.risk.risk_gate import CryptoRiskGate
    monkeypatch.setattr(CryptoRiskGate,'MAX_POSITIONS',1)
    c=Client()
    run(submit_order(OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='position1'),client=c))
    with pytest.raises(OrderExecutionError,match='Position reserv'):
        run(submit_order(OrderRequest(symbol='ETHUSDT',qty=1,client_order_id='position2'),client=c))
    assert c.calls==1


def test_partial_cancel_releases_only_unfilled_reservation():
    from backend.exchange.lifecycle import execute_entry,cancel_trade_order
    c=Client(); c.account['buying_power']=150
    req=OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='release')
    _,t=run(execute_entry(req,client=c))
    c.cancel_order=Mock(return_value={})
    c.get_order_by_client_id=Mock(return_value=ack('CANCELED',1,.4,100))
    run(cancel_trade_order(t,client=c))
    c.account['balances']['SOL']={'free':.4,'total':.4,'value_usdt':40}
    c.account['buying_power']=110
    run(submit_order(OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='next'),client=c))
    assert c.calls==2


@pytest.mark.parametrize('patch',[{'reduce_only':True,'side':'SELL'},{'side':'SELL'}])
def test_entry_route_cannot_create_position_from_inventory_reduction(monkeypatch,patch):
    import backend.api.routes as routes
    c=Client(); c.account['balances']['SOL']={'free':1,'total':1,'value_usdt':100}
    c.get_execution_context=Mock(return_value={'account':c.account,'score':.70,'is_valid':True,'side':'SELL','take_profit':96,'stop_loss':102})
    monkeypatch.setattr(routes,'_binance_client',c)
    response=api.post('/api/exchange/order',json={'symbol':'SOLUSDT','qty':1,**patch})
    assert response.status_code>=400
    assert c.calls==0 and run(trade_log.get_all_trades())==[]


@pytest.mark.parametrize('extra',[{'symbol':'ETHUSDT'},{'side':'SELL'},{'orig_qty':2,'executed_qty':2,'cummulative_quote_qty':200}])
def test_ack_must_match_requested_identity_and_quantity(extra):
    from backend.exchange.execution import parse_acknowledgement
    with pytest.raises(ValueError):
        parse_acknowledgement({**ack(),**extra},OrderRequest(symbol='SOLUSDT',qty=1),100)


def test_legacy_position_partial_close_preserves_residual():
    from backend.exchange.lifecycle import close_trade_position
    t=record(); t.executed_qty=0; t.requested_qty=0; run(trade_log.save_trade(t))
    c=Client(); c.account['balances']['SOL']={'free':1,'total':1,'value_usdt':100}
    c.place_order=Mock(return_value=ack('PARTIALLY_FILLED',1,.4,110))
    updated=run(close_trade_position(t,client=c))
    assert updated.status==TradeStatus.OPEN and updated.proposal.qty==.6


def test_spot_inventory_entry_preview_rejects_short_semantics():
    from backend.exchange.execution import preview_order
    c=Client(); c.account['balances']['SOL']={'free':1,'total':1,'value_usdt':100}
    c.get_execution_context=Mock(return_value={'account':c.account,'score':.70,'is_valid':True,'side':'SELL','stop_loss':102,'take_profit':96})
    result=run(preview_order(OrderRequest(symbol='SOLUSDT',side='SELL',qty=1),client=c))
    assert not result['approved']


def test_partial_close_residual_keeps_exchange_step_precision():
    from backend.exchange.lifecycle import close_trade_position
    t=record(qty=.3); run(trade_log.save_trade(t))
    c=Client(); c.account['balances']['SOL']={'free':.3,'total':.3,'value_usdt':30}
    c.place_order=Mock(return_value=ack('CANCELED',.3,.1,110))
    updated=run(close_trade_position(t,client=c))
    assert updated.proposal.qty==.2


def test_api_cancel_rejection_preserves_pending_exposure(monkeypatch):
    import backend.api.routes as routes
    t=record(); t.status=TradeStatus.PENDING;t.exchange_status='NEW'
    run(trade_log.save_trade(t))
    c=Client();c.cancel_order=Mock(return_value={'error':'outage'})
    monkeypatch.setattr(routes,'get_exchange_client',lambda market:c)
    response=api.delete(f'/api/exchange/orders/{t.trade_id}?market=spot')
    assert response.status_code==502
    assert run(trade_log.get_trade_by_id(t.trade_id)).status==TradeStatus.PENDING


def test_confirmed_rejected_intent_is_not_reported_as_unknown():
    from backend.store import order_intents
    c=Client();c.place_order=Mock(return_value=ack('REJECTED',1,0))
    req=OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='rejected')
    with pytest.raises(OrderExecutionError,match='rejected'):
        run(submit_order(req,client=c))
    assert order_intents.get(req)['status']=='REJECTED'


def test_guardian_partial_close_event_retains_market_and_open_state(monkeypatch):
    import backend.engine.auto_trader as module
    t=record();run(trade_log.save_trade(t))
    c=Client();c.account['balances']['SOL']={'free':1,'total':1,'value_usdt':100}
    c.place_order=Mock(return_value=ack('PARTIALLY_FILLED',1,.4,110))
    emit=Mock();monkeypatch.setattr(module.auto_trader,'_emit_guardian_event',emit)
    module.auto_trader._close_position_and_finalize_trade(c,t,'SOLUSDT',110,100,1,'TAKE_PROFIT','threshold')
    assert emit.call_args.kwargs['market']=='spot'
    assert emit.call_args.kwargs['status']=='OPEN'
    assert emit.call_args.kwargs['trade_id']==t.trade_id


def test_uncertain_cancel_all_does_not_report_success(monkeypatch):
    import backend.api.routes as routes
    c=Client();c.place_order=Mock(side_effect=TimeoutError());c.get_order_by_client_id=Mock(side_effect=TimeoutError())
    with pytest.raises(OrderExecutionError):
        run(submit_order(OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='cancel-unknown'),client=c))
    result=api.post('/api/exchange/cancel-all?market=spot').json()
    assert result['success'] is False and result['errors']


@pytest.mark.parametrize('terminal',['CANCELED','EXPIRED','REJECTED'])
def test_terminal_zero_fill_exit_advances_attempt_for_retry(terminal):
    from backend.exchange.lifecycle import close_trade_position
    t=record();run(trade_log.save_trade(t))
    c=Client();c.account['balances']['SOL']={'free':1,'total':1,'value_usdt':100}
    c.place_order=Mock(return_value=ack(terminal,1,0))
    try: run(close_trade_position(t,client=c))
    except OrderExecutionError: pass
    first_id=c.place_order.call_args.kwargs['client_order_id']
    c.place_order.return_value=ack()
    updated=run(close_trade_position(t,client=c))
    assert c.place_order.call_count==2 and updated.status==TradeStatus.CLOSED
    assert c.place_order.call_args.kwargs['client_order_id']!=first_id


def test_unknown_close_retains_original_attempt_and_payload():
    from backend.exchange.lifecycle import close_trade_position
    t=record();run(trade_log.save_trade(t))
    c=Client();c.account['balances']['SOL']={'free':1,'total':1,'value_usdt':100}
    c.place_order=Mock(side_effect=TimeoutError());c.get_order_by_client_id=Mock(side_effect=TimeoutError())
    with pytest.raises(OrderExecutionError): run(close_trade_position(t,client=c))
    first_id=c.place_order.call_args.kwargs['client_order_id']
    c.get_order_by_client_id=Mock(return_value=ack())
    updated=run(close_trade_position(t,client=c))
    assert updated.status==TradeStatus.CLOSED and c.place_order.call_count==1
    c.get_order_by_client_id.assert_called_once_with('SOLUSDT',first_id)


@pytest.mark.parametrize('first_status',['NEW','UNKNOWN','FILLED'])
def test_futures_claim_rejects_opposite_reserved_entry(first_status):
    from backend.store import order_intents
    import time
    c=Client();c.market='futures';c.account.update(can_trade=True,positions=[])
    c.validate_account_mode=Mock()
    c.get_execution_info=Mock(return_value=dict(status='TRADING',quote_asset='USDT',margin_asset='USDT',contract_type='PERPETUAL',filters=[dict(filterType='LOT_SIZE',minQty='.01',stepSize='.01')]))
    c.get_execution_context=Mock(return_value=dict(account=c.account,score=.7,is_valid=True,side='BUY',stop_loss=98,take_profit=104))
    if first_status=='UNKNOWN':
        c.place_order=Mock(side_effect=TimeoutError());c.get_order_by_client_id=Mock(side_effect=TimeoutError())
    else:
        c.place_order=Mock(return_value=ack(first_status,1,1 if first_status=='FILLED' else 0))
    snapshot_started=time.time()
    try: run(submit_order(OrderRequest(market='futures',symbol='SOLUSDT',qty=1,client_order_id='reserved-long'),client=c))
    except OrderExecutionError: pass
    opposite=OrderRequest(market='futures',symbol='SOLUSDT',side='SELL',qty=1,client_order_id='reserved-short')
    with pytest.raises(ValueError,match='direction'):
        order_intents.claim(opposite,{'quantity':'1','notional':'100'},c.account,snapshot_started)


def test_orchestrator_does_not_rewrite_already_persisted_entry(monkeypatch):
    from types import SimpleNamespace
    import threading
    from backend.agents.orchestrator import TradingOrchestrator,portfolio_store
    from backend.exchange.lifecycle import execute_entry,close_trade_position
    c=Client();c.account['balances']['SOL']={'free':1,'total':1,'value_usdt':100}
    c.place_order=Mock(return_value=ack(oid='entry'))
    _,t=run(execute_entry(OrderRequest(symbol='SOLUSDT',qty=1,client_order_id='orchestrator'),client=c))
    orchestrator=object.__new__(TradingOrchestrator)
    orchestrator.executor=SimpleNamespace(execute=lambda *args:t)
    queued=[]
    class DeferredThread:
        def __init__(self,target,**kw): queued.append(target)
        def start(self): pass
    monkeypatch.setattr(portfolio_store,'add_position',Mock())
    with monkeypatch.context() as context:
        context.setattr(threading,'Thread',DeferredThread)
        orchestrator._node_execute(dict(underlying='SOLUSDT',debate_result=SimpleNamespace(winning_proposal_id=t.proposal.id),proposals=[t.proposal],risk_result=None))
    c.place_order.return_value=ack(oid='exit',price=110)
    run(close_trade_position(t,client=c))
    for target in queued: target()
    stored=run(trade_log.get_trade_by_id(t.trade_id))
    assert stored.status==TradeStatus.CLOSED and stored.closed_qty==1 and stored.realized_pnl==10


def test_orchestrator_records_undispatched_rejection_without_position(monkeypatch):
    from types import SimpleNamespace
    from backend.agents.orchestrator import TradingOrchestrator,portfolio_store
    rejected=record();rejected.status=TradeStatus.CANCELLED;rejected.exchange_status='NOT_DISPATCHED'
    orchestrator=object.__new__(TradingOrchestrator)
    orchestrator.executor=SimpleNamespace(execute=lambda *args:rejected)
    add=Mock();monkeypatch.setattr(portfolio_store,'add_position',add)
    orchestrator._node_execute(dict(underlying='SOLUSDT',debate_result=SimpleNamespace(winning_proposal_id=rejected.proposal.id),proposals=[rejected.proposal],risk_result=None))
    stored=run(trade_log.get_trade_by_id(rejected.trade_id))
    assert stored is not None and stored.status==TradeStatus.CANCELLED
    add.assert_not_called()


def test_concurrent_close_callers_share_one_attempt():
    from backend.exchange.lifecycle import close_trade_position
    t=record();run(trade_log.save_trade(t))
    c=Client();c.account['balances']['SOL']={'free':1,'total':1,'value_usdt':100}
    c.place_order=Mock(return_value=ack());c.get_order_by_client_id=Mock(return_value=ack())
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda _:run(close_trade_position(t,client=c)),range(2)))
    assert c.place_order.call_count==1
    stored=run(trade_log.get_trade_by_id(t.trade_id))
    assert stored.status==TradeStatus.CLOSED and stored.exit_attempt==1


def test_reapplying_terminal_exit_cannot_clear_a_new_attempt():
    from backend.exchange.lifecycle import close_trade_position
    from backend.exchange.schemas import OrderResult
    from backend.store import order_intents
    t=record();run(trade_log.save_trade(t))
    c=Client();c.account['balances']['SOL']={'free':1,'total':1,'value_usdt':100}
    c.place_order=Mock(return_value=ack('CANCELED',1,0))
    run(close_trade_position(t,client=c))
    old_id=c.place_order.call_args.kwargs['client_order_id']
    old=OrderResult.model_validate_json(order_intents.lookup('spot',old_id)['result'])
    prepared=run(trade_log.prepare_exit(t.trade_id))
    reapplied=run(trade_log.apply_exit(t.trade_id,old))
    assert reapplied.exit_client_order_id==prepared.exit_client_order_id!=old_id
    assert reapplied.exit_attempt==1


def test_opposite_futures_concurrent_claims_cannot_both_reserve():
    from backend.store import order_intents
    import time
    account={'equity':10000,'buying_power':10000,'positions':[]}
    started=time.time()
    def claim(side):
        request=OrderRequest(market='futures',symbol='SOLUSDT',side=side,qty=1,client_order_id=side)
        try:
            order_intents.claim(request,{'quantity':'1','notional':'100'},account,started)
            return True
        except ValueError: return False
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(claim,['BUY','SELL']))
    assert sum(results)==1
