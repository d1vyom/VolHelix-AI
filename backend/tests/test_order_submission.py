import asyncio
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from backend.main import fastapi_app
from backend.store.trade_log import trade_log
import backend.api.routes as routes

client = TestClient(fastapi_app)

@pytest.fixture
def orders(monkeypatch, exchange_fixture):
    monkeypatch.setattr(routes, '_binance_client', exchange_fixture)
    import backend.api.websocket as websocket
    emit = AsyncMock()
    monkeypatch.setattr(websocket.sio, 'emit', emit)
    return exchange_fixture, emit

@pytest.mark.parametrize('failure', [RuntimeError('rejected'), {'error': 'insufficient balance', 'status': 'REJECTED'}, {'status': 'ERROR'}, {'status': 'NEW'}])
def test_rejected_order_is_not_persisted(orders, failure, monkeypatch):
    exchange, emit = orders
    from unittest.mock import Mock
    dispatch = Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=failure)
    monkeypatch.setattr(exchange, 'place_order', dispatch)
    response = client.post('/api/exchange/order', json={'symbol':'SOLUSDT','qty':0.5})
    assert response.status_code >= 400
    assert asyncio.run(trade_log.get_all_trades()) == []
    emit.assert_not_awaited()

@pytest.mark.parametrize('patch', [{'qty':0}, {'qty':-1}, {'qty':'NaN'}, {'qty':'Infinity'}, {'quote_quantity':0}, {'quote_quantity':-1}, {'quote_quantity':'NaN'}, {'side':'hold'}, {'order_type':'stop'}, {'order_type':'limit'}, {'limit_price':0}, {'limit_price':'Infinity'}])
def test_invalid_order_never_dispatches(orders, patch):
    exchange, _ = orders
    response = client.post('/api/exchange/order', json={'symbol':'SOLUSDT','qty':0.5, **patch})
    assert response.status_code == 422
    exchange.trading_client.create_order.assert_not_called()

@pytest.mark.parametrize('price', [None, '0', 'NaN', 'Infinity'])
def test_missing_or_invalid_quote_never_dispatches(orders, price):
    exchange, _ = orders
    exchange.market_client.get_symbol_ticker.return_value = {} if price is None else {'price':price}
    response = client.post('/api/exchange/order', json={'symbol':'SOLUSDT','qty':0.5})
    assert response.status_code == 503
    exchange.trading_client.create_order.assert_not_called()

@pytest.mark.parametrize('status,executed,quote,expected', [('NEW','0','0','PENDING'),('PARTIALLY_FILLED','0.2','32','PENDING'),('FILLED','0.5','80','OPEN')])
def test_acknowledgement_uses_actual_fills(orders, status, executed, quote, expected):
    exchange, emit = orders
    exchange.trading_client.create_order.side_effect = None
    exchange.trading_client.create_order.return_value = {'orderId':123,'symbol':'SOLUSDT','side':'BUY','type':'MARKET','status':status,'origQty':'0.5','executedQty':executed,'cummulativeQuoteQty':quote,'fills':[]}
    response = client.post('/api/exchange/order', json={'symbol':'SOLUSDT','quote_quantity':80})
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == expected
    assert data['exchange_status'] == status
    assert data['executed_qty'] == float(executed)
    trade = asyncio.run(trade_log.get_trade_by_id('spot:SOLUSDT:123'))
    assert trade.proposal.qty == float(executed)
    assert trade.entry_price == (160 if float(executed) else 0)
    assert trade.exchange_status == status
    if status != 'FILLED':
        assert not any(call.args[0] == 'trade_executed' for call in emit.await_args_list)

def test_sync_exchange_work_runs_off_event_loop(orders, monkeypatch):
    import threading
    exchange, _ = orders
    from backend.exchange.execution import submit_order
    from backend.exchange.schemas import OrderRequest
    loop_thread = threading.get_ident()
    def quote(symbol):
        assert threading.get_ident() != loop_thread
        return {'price':'150'}
    def dispatch(**kwargs):
        assert threading.get_ident() != loop_thread
        return {'order_id':123,'status':'NEW','orig_qty':0.5}
    monkeypatch.setattr(exchange, 'get_price', quote)
    monkeypatch.setattr(exchange, 'place_order', dispatch)
    result = asyncio.run(submit_order(OrderRequest(symbol='SOLUSDT',qty=0.5), client=exchange))
    assert result.exchange_status == 'NEW'

@pytest.mark.parametrize('status,executed,quote', [('FILLED','0','0'), ('FILLED','0.5','0'),('PARTIALLY_FILLED','0.5','NaN'),('REJECTED','0','0')])
def test_inconsistent_acknowledgement_is_not_persisted(orders,status,executed,quote):
    exchange, emit = orders
    exchange.trading_client.create_order.side_effect = None
    exchange.trading_client.create_order.return_value = {'orderId':123,'symbol':'SOLUSDT','side':'BUY','type':'MARKET','status':status,'origQty':'0.5','executedQty':executed,'cummulativeQuoteQty':quote}
    response = client.post('/api/exchange/order', json={'symbol':'SOLUSDT','qty':0.5})
    assert response.status_code == 502
    assert asyncio.run(trade_log.get_all_trades()) == []
    emit.assert_not_awaited()

@pytest.mark.parametrize('fills', [
    [{'qty':'0.1','price':'160'}],
    [{'qty':'0.6','price':'160'}],
    [{'qty':'0.5','price':'0'}],
    [{'qty':'0.5','price':'NaN'}],
    [{'qty':'0.5','price':'Infinity'}],
    [{'qty':'-0.1','price':'160'}, {'qty':'0.6','price':'160'}],
])
def test_invalid_fill_fallback_never_persists(orders, fills):
    exchange, emit = orders
    exchange.trading_client.create_order.side_effect = None
    exchange.trading_client.create_order.return_value = {'orderId':123,'symbol':'SOLUSDT','side':'BUY','type':'MARKET','status':'FILLED','origQty':'0.5','executedQty':'0.5','fills':fills}
    response = client.post('/api/exchange/order', json={'symbol':'SOLUSDT','qty':0.5})
    assert response.status_code == 502
    assert asyncio.run(trade_log.get_all_trades()) == []
    emit.assert_not_awaited()

@pytest.mark.parametrize('status,executed,original', [
    ('FILLED','1','0.5'), ('FILLED','0.2','0.5'),
    ('NEW','0.5','0.5'), ('PENDING_NEW','0.1','0.5'),
    ('PARTIALLY_FILLED','0','0.5'), ('PARTIALLY_FILLED','0.5','0.5'),
    ('PARTIALLY_FILLED','0.6','0.5'), ('FILLED','0.5','0'),
    ('NEW','0','0'), ('FILLED','0.5',None),
])
def test_contradictory_execution_never_persists(orders, status, executed, original):
    exchange, emit = orders
    exchange.trading_client.create_order.side_effect = None
    exchange.trading_client.create_order.return_value = {'orderId':123,'symbol':'SOLUSDT','side':'BUY','type':'MARKET','status':status,'origQty':original,'executedQty':executed,'cummulativeQuoteQty':str(float(executed)*160)}
    response = client.post('/api/exchange/order', json={'symbol':'SOLUSDT','qty':0.5})
    assert response.status_code == 502
    assert asyncio.run(trade_log.get_all_trades()) == []
    emit.assert_not_awaited()


def test_complete_fill_fallback_uses_weighted_actual_price(orders):
    exchange, _ = orders
    exchange.trading_client.create_order.side_effect = None
    exchange.trading_client.create_order.return_value = {'orderId':123,'symbol':'SOLUSDT','side':'BUY','type':'MARKET','status':'FILLED','origQty':'0.5','executedQty':'0.5','fills':[{'qty':'0.2','price':'150'},{'qty':'0.3','price':'160'}]}
    response = client.post('/api/exchange/order', json={'symbol':'SOLUSDT','qty':0.5})
    assert response.status_code == 200
    trade = asyncio.run(trade_log.get_trade_by_id('spot:SOLUSDT:123'))
    assert trade.entry_price == 156
    assert trade.executed_qty == 0.5
