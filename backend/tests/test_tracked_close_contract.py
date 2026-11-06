import asyncio
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from backend.main import fastapi_app
from backend.tests.test_execution_risk import Client
from backend.tests.test_market_lifecycle import record,ack
from backend.models.market import TradeStatus
from backend.store.trade_log import trade_log
from backend.exchange.execution import validate_order
from backend.exchange.schemas import OrderRequest

api=TestClient(fastapi_app)
def run(coro): return asyncio.run(coro)

def setup(monkeypatch,qty=.9999):
    c=Client();c.account['balances']['SOL']={'free':qty,'total':qty,'value_usdt':qty*100}
    t=record(qty=qty);t.executed_qty=1;t.fees_known=True;t.base_asset='SOL';t.entry_fees={'SOL':1-qty}
    run(trade_log.save_trade(t))
    monkeypatch.setattr('backend.api.routes.get_exchange_client',lambda market:c)
    monkeypatch.setattr('backend.exchange.registry.get_exchange_client',lambda market:c)
    return c,t

def payload(t,identity='close-confirmed'):
    return dict(market=t.market,symbol=t.proposal.symbol,trade_id=t.trade_id,client_order_id=identity)

def test_server_close_preview_rounds_only_tracked_exit(monkeypatch):
    c,t=setup(monkeypatch)
    response=api.post('/api/exchange/close-position/preview',json=payload(t))
    assert response.status_code==200
    preview=response.json()
    assert preview['approved'] and float(preview['quantity'])==.99
    assert float(preview['retained_quantity'])==pytest.approx(.0099)
    assert not validate_order(OrderRequest(symbol='SOLUSDT',qty=.9999),client=c)['approved']
    c.place_order=Mock(return_value=ack(qty=.99,executed=.99,oid='exit'))
    closed=api.post('/api/exchange/close-position',json=payload(t)).json()
    assert c.place_order.call_args.kwargs['quantity']==float(preview['quantity'])
    assert closed['qty']==pytest.approx(.0099)

def test_subminimum_dust_preview_is_honest_and_never_dispatches(monkeypatch):
    c,t=setup(monkeypatch,.0099);c.place_order=Mock()
    p=api.post('/api/exchange/close-position/preview',json=payload(t)).json()
    assert p['approved'] is False and float(p['quantity'])==0
    assert float(p['retained_quantity'])==pytest.approx(.0099)
    assert api.post('/api/exchange/close-position',json=payload(t)).json()['detail']['outcome']=='NOT_DISPATCHED'
    c.place_order.assert_not_called()

@pytest.mark.parametrize('status,executed',[('FILLED',1),('CANCELED',.4)])
def test_close_replay_and_reconcile_original_terminal_attempt(monkeypatch,status,executed):
    c,t=setup(monkeypatch,1)
    c.place_order=Mock(return_value=ack(status,1,executed,oid='exit'))
    body=payload(t)
    first=api.post('/api/exchange/close-position',json=body)
    assert first.status_code==200
    assert c.place_order.call_args.kwargs['client_order_id']==body['client_order_id']
    # Lost response: repeat original identity even when fully closed or terminal partial.
    second=api.post('/api/exchange/close-position',json=body)
    assert second.status_code==200
    recovered=api.post('/api/market/order-intents/close-confirmed/reconcile?market=spot')
    assert recovered.status_code==200 and recovered.json()['executed_qty']==executed
    assert c.place_order.call_count==1
    assert run(trade_log.get_trade_by_id(t.trade_id)).closed_qty==executed

def test_partial_entry_preview_does_not_cancel_but_confirm_reconciles_final_qty(monkeypatch):
    c,t=setup(monkeypatch,.4)
    t.status=TradeStatus.PENDING;t.exchange_status='PARTIALLY_FILLED';t.executed_qty=.4;t.entry_fees={};t.requested_qty=1
    run(trade_log.save_trade(t))
    c.cancel_order=Mock(return_value=ack('CANCELED',1,.6))
    c.get_order=Mock(return_value=dict(ack('CANCELED',1,.6),base_asset='SOL',fees_known=True))
    c.account['balances']['SOL']['free']=.6
    c.place_order=Mock(return_value=ack(qty=.6,executed=.6,oid='exit'))
    p=api.post('/api/exchange/close-position/preview',json=payload(t)).json()
    assert p['approved'] and p['entry_cancellation_required'] is True
    c.cancel_order.assert_not_called()
    r=api.post('/api/exchange/close-position',json=payload(t))
    assert r.status_code==200
    assert c.cancel_order.call_count==1 and c.get_order.call_count==1
    assert c.place_order.call_args.kwargs['quantity']==.6

def test_unknown_close_retains_identity_across_retry(monkeypatch):
    c,t=setup(monkeypatch,1)
    c.place_order=Mock(side_effect=TimeoutError());c.get_order_by_client_id=Mock(side_effect=TimeoutError())
    body=payload(t)
    assert api.post('/api/exchange/close-position',json=body).status_code==502
    assert api.post('/api/exchange/close-position',json=body).status_code==502
    assert c.place_order.call_count==1
    c.get_order_by_client_id.return_value=ack(oid='exit');c.get_order_by_client_id.side_effect=None
    assert api.post('/api/market/order-intents/close-confirmed/reconcile?market=spot').status_code==200
    assert c.place_order.call_count==1


def test_precheck_failure_is_durable_and_fresh_confirmation_can_close(monkeypatch):
    c,t=setup(monkeypatch,1);c.account['balances']['SOL']['free']=0
    c.place_order=Mock(return_value=ack(oid='exit'));c.cancel_order=Mock()
    first=api.post('/api/exchange/close-position',json=payload(t))
    assert first.json()['detail']['outcome']=='NOT_DISPATCHED'
    recovered=api.post('/api/market/order-intents/close-confirmed/reconcile?market=spot')
    assert recovered.json()['detail']['outcome']=='NOT_DISPATCHED'
    c.place_order.assert_not_called();c.cancel_order.assert_not_called()
    assert run(trade_log.get_trade_by_id(t.trade_id)).exit_client_order_id is None
    c.account['balances']['SOL']['free']=1
    assert api.post('/api/exchange/close-position',json=payload(t,'fresh-confirmation')).status_code==200
    assert c.place_order.call_count==1
    replay=api.post('/api/exchange/close-position',json=payload(t))
    assert replay.json()['detail']['outcome']=='NOT_DISPATCHED' and c.place_order.call_count==1


def test_no_close_record_reconcile_is_query_only_and_unknown(monkeypatch):
    c,t=setup(monkeypatch,1);c.place_order=Mock();c.cancel_order=Mock();c.get_order_by_client_id=Mock()
    response=api.post('/api/market/order-intents/not-received/reconcile?market=spot')
    assert response.status_code==404
    c.place_order.assert_not_called();c.cancel_order.assert_not_called();c.get_order_by_client_id.assert_not_called()


def test_stale_account_cannot_reconcile_completed_close(monkeypatch):
    from backend.config import settings
    c,t=setup(monkeypatch,1);c.place_order=Mock(return_value=ack(oid='exit'))
    assert api.post('/api/exchange/close-position',json=payload(t)).status_code==200
    monkeypatch.setattr(settings,'BINANCE_API_KEY','different-account')
    response=api.post('/api/market/order-intents/close-confirmed/reconcile?market=spot')
    assert response.json()['detail']['outcome']=='UNKNOWN' and c.place_order.call_count==1


def test_dust_close_response_loss_has_truthful_durable_no_dispatch(monkeypatch):
    c,t=setup(monkeypatch,.0099);c.place_order=Mock()
    response=api.post('/api/exchange/close-position',json=payload(t))
    assert response.json()['detail']['outcome']=='NOT_DISPATCHED'
    response=api.post('/api/market/order-intents/close-confirmed/reconcile?market=spot')
    assert response.json()['detail']['outcome']=='NOT_DISPATCHED'
    assert run(trade_log.get_trade_by_id(t.trade_id)).proposal.qty==.0099
    c.place_order.assert_not_called()


def test_cancel_without_fill_has_durable_no_exit_dispatch(monkeypatch):
    c,t=setup(monkeypatch,0);t.status=TradeStatus.PENDING;t.exchange_status='NEW';t.executed_qty=0;t.requested_qty=1;t.entry_fees={}
    run(trade_log.save_trade(t))
    c.cancel_order=Mock(return_value=ack('CANCELED',1,0));c.get_order=Mock(return_value=ack('CANCELED',1,0));c.place_order=Mock()
    assert api.post('/api/exchange/close-position',json=payload(t)).json()['detail']['outcome']=='NOT_DISPATCHED'
    assert api.post('/api/market/order-intents/close-confirmed/reconcile?market=spot').json()['detail']['outcome']=='NOT_DISPATCHED'
    assert c.cancel_order.call_count==1 and run(trade_log.get_trade_by_id(t.trade_id)).proposal.qty==0
    c.place_order.assert_not_called()


def test_no_dispatch_proof_cannot_release_a_dispatch_claim(monkeypatch):
    from backend.store import order_intents
    c,t=setup(monkeypatch,1);t=run(trade_log.prepare_exit(t.trade_id,client_order_id='close-race'))
    order_intents.bind_account(c,'spot')
    request=OrderRequest(symbol='SOLUSDT',side='SELL',qty=1,reduce_only=True,client_order_id='close-race')
    order_intents.claim(request,{'quantity':'1','notional':'100'},c.account,0)
    assert not order_intents.record_close_not_dispatched(t.trade_id,'spot','SOLUSDT','close-race','Failed validation')
    assert run(trade_log.get_trade_by_id(t.trade_id)).exit_client_order_id=='close-race'
    assert order_intents.lookup('spot','close-race')['status']=='DISPATCHING'


def test_no_dispatch_proof_blocks_late_claim_for_same_id(monkeypatch):
    from backend.store import order_intents
    c,t=setup(monkeypatch,1);run(trade_log.prepare_exit(t.trade_id,client_order_id='close-race'))
    order_intents.bind_account(c,'spot')
    assert order_intents.record_close_not_dispatched(t.trade_id,'spot','SOLUSDT','close-race','Failed validation')
    with pytest.raises(ValueError,match='not dispatched'):
        order_intents.claim(OrderRequest(symbol='SOLUSDT',side='SELL',qty=1,reduce_only=True,client_order_id='close-race'),{'quantity':'1','notional':'100'},c.account,0)
    assert order_intents.lookup('spot','close-race') is None


def test_preview_does_not_claim_net_quantity_when_commissions_unknown(monkeypatch):
    c,t=setup(monkeypatch,1);t.fees_known=None;run(trade_log.save_trade(t))
    c.get_order_fills=Mock(side_effect=TimeoutError());c.place_order=Mock();c.cancel_order=Mock()
    response=api.post('/api/exchange/close-position/preview',json=payload(t)).json()
    assert response['approved'] is False and 'commission' in response['reason'].lower()
    c.place_order.assert_not_called();c.cancel_order.assert_not_called()
