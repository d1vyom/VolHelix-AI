"""HTTP outcomes and server-owned durable intent reconciliation, without exchange I/O."""
from unittest.mock import Mock

import pytest

from backend.tests.test_market_lifecycle import api, run, ack
from backend.tests.test_execution_risk import Client
from backend.exchange.execution import submit_order, OrderExecutionError
from backend.exchange.schemas import OrderRequest
from backend.store import order_intents
from backend.store.trade_log import trade_log


def bind_clients(monkeypatch, client):
    import backend.api.routes as routes
    import backend.exchange.registry as registry
    monkeypatch.setattr(routes, 'get_exchange_client', lambda market: client)
    monkeypatch.setattr(registry, 'get_exchange_client', lambda market: client)


def test_approved_preview_then_durable_rejection_is_machine_readable_on_every_retry(monkeypatch):
    client = Client(); bind_clients(monkeypatch, client)
    request = OrderRequest(symbol='SOLUSDT', qty=1, client_order_id='known-rejection')
    assert api.post('/api/market/order/preview', json=request.model_dump()).json()['approved']
    client.place_order = Mock(return_value=ack('REJECTED', 1, 0))
    for _ in range(2):
        response = api.post('/api/exchange/order', json=request.model_dump())
        assert response.status_code == 502
        assert response.json()['detail']['outcome'] == 'REJECTED'
        assert response.json()['detail']['client_order_id'] == 'known-rejection'
    assert client.place_order.call_count == 1
    assert run(trade_log.get_all_trades()) == []
    assert order_intents.lookup('spot', 'known-rejection')['status'] == 'REJECTED'


def test_execution_risk_rejection_after_approved_preview_is_not_dispatched(monkeypatch):
    client = Client(); bind_clients(monkeypatch, client)
    request = OrderRequest(symbol='SOLUSDT', qty=1, client_order_id='risk-changed')
    assert api.post('/api/market/order/preview', json=request.model_dump()).json()['approved']
    client.score = .69
    response = api.post('/api/exchange/order', json=request.model_dump())
    assert response.status_code == 502
    assert response.json()['detail']['outcome'] == 'NOT_DISPATCHED'
    assert client.calls == 0
    assert run(trade_log.get_all_trades()) == []


def test_true_unknown_retry_keeps_original_payload_and_never_creates_twice(monkeypatch):
    client = Client(); bind_clients(monkeypatch, client)
    client.place_order = Mock(side_effect=TimeoutError())
    client.get_order_by_client_id = Mock(side_effect=TimeoutError())
    request = OrderRequest(symbol='SOLUSDT', qty=1, order_type='LIMIT', limit_price=100, client_order_id='uncertain')
    for _ in range(2):
        response = api.post('/api/exchange/order', json=request.model_dump())
        assert response.status_code == 502
        assert response.json()['detail']['outcome'] == 'UNKNOWN'
    assert client.place_order.call_count == 1
    assert order_intents.lookup('spot', 'uncertain')['payload'] == request.model_dump_json()
    assert order_intents.lookup('spot', 'uncertain')['status'] == 'UNKNOWN'


@pytest.mark.parametrize('market', ['spot', 'futures'])
def test_intent_only_row_reconciles_stored_payload_in_selected_market_without_create(monkeypatch, market):
    client = Client(); bind_clients(monkeypatch, client)
    request = OrderRequest(market=market, symbol='SOLUSDT', qty=1, order_type='LIMIT', limit_price=100, client_order_id='same-id')
    # Durable claims model a crash after dispatch, before a TradeRecord exists.
    order_intents.bind_account(client, market)
    order_intents.claim(request, {'quantity':'1', 'notional':'100'}, client.account, 0)
    client.place_order = Mock(side_effect=AssertionError('Reconciliation must never dispatch'))
    client.get_order_by_client_id = Mock(return_value=ack('FILLED', 1, 1, 103))
    other = 'futures' if market == 'spot' else 'spot'
    assert api.post(f'/api/market/order-intents/same-id/reconcile?market={other}').status_code == 404
    assert client.get_order_by_client_id.call_count == 0
    response = api.post(f'/api/market/order-intents/same-id/reconcile?market={market}')
    assert response.status_code == 200
    assert response.json()['outcome'] == 'ACKNOWLEDGED'
    assert response.json()['market'] == market
    assert response.json()['executed_qty'] == 1
    client.get_order_by_client_id.assert_called_once_with('SOLUSDT', 'same-id')
    client.place_order.assert_not_called()
    trades = run(trade_log.get_all_trades())
    assert len(trades) == 1 and trades[0].market == market
    assert trades[0].entry_price == 103 and trades[0].proposal.qty == 1
    assert order_intents.lookup(market, 'same-id')['payload'] == request.model_dump_json()


@pytest.mark.parametrize('status', ['UNKNOWN', 'DISPATCHING'])
def test_unresolved_server_reconciliation_preserves_intent_and_reservation(monkeypatch, status):
    client = Client(); bind_clients(monkeypatch, client)
    request = OrderRequest(symbol='SOLUSDT', qty=1, client_order_id='reserved')
    order_intents.bind_account(client, 'spot')
    order_intents.claim(request, {'quantity':'1', 'notional':'100'}, client.account, 0)
    if status == 'UNKNOWN': order_intents.finish(request)
    client.place_order = Mock(side_effect=AssertionError('No redispatch'))
    client.get_order_by_client_id = Mock(side_effect=TimeoutError())
    response = api.post('/api/market/order-intents/reserved/reconcile?market=spot')
    assert response.status_code == 502
    assert response.json()['detail']['outcome'] == 'UNKNOWN'
    row = order_intents.lookup('spot', 'reserved')
    assert row['status'] == status and row['quantity'] == 1 and row['notional'] == 100
    assert row['payload'] == request.model_dump_json()
    assert run(trade_log.get_all_trades()) == []
    client.place_order.assert_not_called()


def test_server_reconciliation_of_durable_rejection_returns_proven_outcome(monkeypatch):
    client = Client(); bind_clients(monkeypatch, client)
    request = OrderRequest(symbol='SOLUSDT', qty=1, client_order_id='rejected-reload')
    client.place_order = Mock(return_value=ack('REJECTED', 1, 0))
    with pytest.raises(OrderExecutionError): run(submit_order(request, client=client))
    client.get_order_by_client_id = Mock(side_effect=AssertionError('Known result needs no exchange call'))
    response = api.post('/api/market/order-intents/rejected-reload/reconcile?market=spot')
    assert response.status_code == 502
    assert response.json()['detail']['outcome'] == 'REJECTED'
    assert client.place_order.call_count == 1
    client.get_order_by_client_id.assert_not_called()


@pytest.mark.parametrize('status,executed', [('FILLED', 1), ('REJECTED', 0)])
def test_exit_intent_reconciliation_updates_only_original_tracked_position(monkeypatch, status, executed):
    from backend.tests.test_market_lifecycle import record
    client = Client(); bind_clients(monkeypatch, client)
    trade = record(); run(trade_log.save_trade(trade))
    trade = run(trade_log.prepare_exit(trade.trade_id))
    request = OrderRequest(symbol='SOLUSDT', qty=1, side='SELL', reduce_only=True, client_order_id=trade.exit_client_order_id)
    client.account['balances']['SOL'] = {'free':1, 'total':1, 'value_usdt':100}
    order_intents.bind_account(client, 'spot')
    order_intents.claim(request, {'quantity':'1', 'notional':'100'}, client.account, 0)
    client.place_order = Mock(side_effect=AssertionError('Reconciliation cannot create an exit'))
    client.get_order_by_client_id = Mock(return_value=ack(status, 1, executed, 110, oid='exit-8'))
    response = api.post(f'/api/market/order-intents/{request.client_order_id}/reconcile?market=spot')
    assert response.status_code == (200 if status == 'FILLED' else 502)
    repeated = api.post(f'/api/market/order-intents/{request.client_order_id}/reconcile?market=spot')
    assert repeated.status_code == response.status_code
    assert repeated.json().get('outcome', repeated.json().get('detail', {}).get('outcome')) == ('ACKNOWLEDGED' if status == 'FILLED' else 'REJECTED')
    rows = run(trade_log.get_all_trades())
    assert len(rows) == 1 and rows[0].trade_id == trade.trade_id
    assert rows[0].proposal.qty == 1-executed
    assert rows[0].realized_pnl == executed*10
    assert rows[0].exit_client_order_id is None
    client.place_order.assert_not_called()


def test_reconcile_account_mismatch_retains_unknown_and_original_reservation(monkeypatch):
    from types import SimpleNamespace
    client = Client(); bind_clients(monkeypatch, client)
    client.trading_client = SimpleNamespace(API_KEY='original-test-only-account')
    request = OrderRequest(symbol='SOLUSDT', qty=1, client_order_id='account-pinned')
    order_intents.bind_account(client, 'spot')
    order_intents.claim(request, {'quantity':'1', 'notional':'100'}, client.account, 0)
    client.trading_client.API_KEY = 'changed-test-only-account'
    client.place_order = Mock(side_effect=AssertionError('No redispatch'))
    client.get_order_by_client_id = Mock(side_effect=AssertionError('Wrong account must not query'))
    response = api.post('/api/market/order-intents/account-pinned/reconcile?market=spot')
    assert response.status_code == 502
    assert response.json()['detail']['outcome'] == 'UNKNOWN'
    assert order_intents.lookup('spot', 'account-pinned')['status'] == 'DISPATCHING'
    client.place_order.assert_not_called(); client.get_order_by_client_id.assert_not_called()


def test_ticket_retry_account_a_b_a_preserves_original_unknown_until_confirmed(monkeypatch):
    from types import SimpleNamespace
    original = Client(); original.trading_client = SimpleNamespace(API_KEY='test-only-account-A')
    changed = Client(); changed.trading_client = SimpleNamespace(API_KEY='test-only-account-B')
    original.place_order = Mock(side_effect=TimeoutError())
    original.get_order_by_client_id = Mock(side_effect=TimeoutError())
    changed.place_order = Mock(side_effect=AssertionError('Wrong account cannot create'))
    changed.get_order_by_client_id = Mock(side_effect=AssertionError('Wrong account cannot query'))
    bind_clients(monkeypatch, original)
    request = OrderRequest(symbol='SOLUSDT', qty=1, order_type='LIMIT', limit_price=100, client_order_id='ticket-account-retry')
    first = api.post('/api/exchange/order', json=request.model_dump())
    assert first.json()['detail']['outcome'] == 'UNKNOWN'
    before = order_intents.lookup('spot', request.client_order_id)
    bind_clients(monkeypatch, changed)
    retry = api.post('/api/exchange/order', json=request.model_dump())
    assert retry.status_code == 502 and retry.json()['detail']['outcome'] == 'UNKNOWN'
    assert order_intents.lookup('spot', request.client_order_id) == before
    changed.place_order.assert_not_called(); changed.get_order_by_client_id.assert_not_called()
    assert original.place_order.call_count == 1
    bind_clients(monkeypatch, original)
    original.get_order_by_client_id = Mock(return_value=ack('FILLED', 1, 1, 99))
    recovered = api.post('/api/exchange/order', json=request.model_dump())
    assert recovered.status_code == 200 and recovered.json()['outcome'] == 'ACKNOWLEDGED'
    assert recovered.json()['exchange_status'] == 'FILLED' and recovered.json()['entry_price'] == 99
    assert original.place_order.call_count == 1
    assert order_intents.lookup('spot', request.client_order_id)['payload'] == request.model_dump_json()


def test_ticket_payload_conflict_does_not_prove_original_unknown_was_never_dispatched(monkeypatch):
    client = Client(); bind_clients(monkeypatch, client)
    client.place_order = Mock(side_effect=TimeoutError())
    client.get_order_by_client_id = Mock(side_effect=TimeoutError())
    request = OrderRequest(symbol='SOLUSDT', qty=1, client_order_id='original-unknown')
    assert api.post('/api/exchange/order', json=request.model_dump()).json()['detail']['outcome'] == 'UNKNOWN'
    before = order_intents.lookup('spot', request.client_order_id)
    queries = client.get_order_by_client_id.call_count
    conflict = api.post('/api/exchange/order', json=request.model_copy(update={'qty':2}).model_dump())
    assert conflict.status_code == 409 and conflict.json()['detail']['outcome'] == 'UNKNOWN'
    assert order_intents.lookup('spot', request.client_order_id) == before
    assert client.place_order.call_count == 1 and client.get_order_by_client_id.call_count == queries
