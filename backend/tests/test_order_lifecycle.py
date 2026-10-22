import pytest
import asyncio
from backend.models.market import TradeStatus, StrategyType, OrderType
from backend.models.trade import TradeProposal, TradeRecord
from backend.store.trade_log import trade_log
from backend.utils.market_hours import get_market_clock, is_market_open
from fastapi.testclient import TestClient
from backend.main import fastapi_app

client = TestClient(fastapi_app)


@pytest.fixture(autouse=True)
def lifecycle_exchange(monkeypatch, exchange_fixture):
    """Explicit SDK responses; API handlers, adapter and SQLite stay real."""
    import backend.api.routes as routes
    from itertools import count
    ids = count(1001)
    sdk = exchange_fixture.trading_client
    sdk.get_account.side_effect = None
    sdk.get_account.return_value = {
        "canTrade": True,
        "balances": [
            {"asset": "USDT", "free": "10000", "locked": "0"},
            {"asset": "SOL", "free": "0.5", "locked": "0"},
        ],
    }

    def order_response(**params):
        qty = str(params.get("quantity", "0"))
        price = params.get("price", "150.00")
        market = params["type"] == "MARKET"
        return {
            "orderId": next(ids), "symbol": params["symbol"],
            "side": params["side"], "type": params["type"],
            "status": "FILLED" if market else "NEW",
            "price": price, "origQty": qty,
            "executedQty": qty if market else "0",
            "cummulativeQuoteQty": str(float(qty) * float(price)) if market else "0",
            "timeInForce": params.get("timeInForce", "GTC"),
            "fills": [{"price": price, "qty": qty, "commission": "0", "commissionAsset": "USDT", "tradeId": 1}] if market else [],
        }

    sdk.create_order.side_effect = order_response
    monkeypatch.setattr(routes, "_binance_client", exchange_fixture)


def test_market_clock_reports_continuous_session():
    asyncio.run(trade_log.init_db())

    # Crypto trades 24/7: the clock is informational and never gates execution.
    clock = get_market_clock()
    assert clock["is_open"] is True
    assert "current_time_et" in clock
    assert clock["market"] == "CRYPTO_24_7"
    assert "24/7" in clock.get("reason", "")
    assert is_market_open() is True

    # No equity-era session override exists any more.
    assert "simulation_active" not in clock
    assert "simulation_override" not in clock

def test_order_lifecycle_market_and_limit():
    asyncio.run(trade_log.init_db())

    test_sym = "SOLUSDT"
    lmt_sym = "BNBUSDT"

    # 1. Test Market Order submission via API
    res = client.post("/api/exchange/order", json={
        "symbol": test_sym,
        "qty": 0.5,
        "side": "buy",
        "order_type": "market"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["status"] == "OPEN"
    assert data["order_type"] == "MARKET"
    assert data["qty"] == 0.5
    market_order_id = data["trade_id"]

    # Verify market order appears in open positions
    open_trades = asyncio.run(trade_log.get_open_trades())
    open_ids = [t.trade_id for t in open_trades]
    assert market_order_id in open_ids

    # 2. Test Limit Order submission via API
    res_lmt = client.post("/api/exchange/order", json={
        "symbol": lmt_sym,
        "qty": 0.1,
        "side": "buy",
        "order_type": "limit",
        "limit_price": 550.00
    })
    assert res_lmt.status_code == 200
    lmt_data = res_lmt.json()
    assert lmt_data["success"] is True
    assert lmt_data["status"] == "PENDING"
    assert lmt_data["order_type"] == "LIMIT"
    assert lmt_data["limit_price"] == 550.00
    limit_order_id = lmt_data["trade_id"]

    # Verify limit order appears in pending trades, NOT open trades
    pending_trades = asyncio.run(trade_log.get_pending_trades())
    pending_ids = [t.trade_id for t in pending_trades]
    assert limit_order_id in pending_ids

    open_trades_after = asyncio.run(trade_log.get_open_trades())
    assert limit_order_id not in [t.trade_id for t in open_trades_after]

    # 3. Test Fill Pending Limit Order via API
    # Manual fill prices cannot authorize executions. Supply a real SDK status
    # response and reconcile without a synthetic fill instruction.
    exchange = __import__('backend.api.routes',fromlist=['_binance_client'])._binance_client
    exchange.trading_client.get_order.side_effect = None
    exchange.trading_client.get_order.return_value = {
        'orderId':lmt_data['order_id'],'status':'FILLED','origQty':'0.1',
        'executedQty':'0.1','cummulativeQuoteQty':'54.95',
        'fills':[{'qty':'.1','price':'549.5','commission':'0','commissionAsset':'USDT'}]}
    fill_res = client.post(f"/api/trades/{limit_order_id}/fill", json={})
    assert fill_res.status_code == 200
    fill_data = fill_res.json()
    assert fill_data["success"] is True
    assert fill_data["status"] == "OPEN"

    # Verify it moved from Pending to Open (Positions)
    pending_now = asyncio.run(trade_log.get_pending_trades())
    assert limit_order_id not in [t.trade_id for t in pending_now]

    open_now = asyncio.run(trade_log.get_open_trades())
    assert limit_order_id in [t.trade_id for t in open_now]

    # 4. Test Close Position -> moves to History
    close_res = client.post("/api/exchange/close-position", json={
        "symbol": test_sym
    })
    assert close_res.status_code == 200
    close_data = close_res.json()
    assert close_data["success"] is True
    assert close_data["status"] == "CLOSED"

    # Verify test_sym is no longer in open trades, but in history trades
    open_final = asyncio.run(trade_log.get_open_trades())
    assert market_order_id not in [t.trade_id for t in open_final]

    history_trades = asyncio.run(trade_log.get_history_trades())
    history_ids = [t.trade_id for t in history_trades]
    assert market_order_id in history_ids

def test_crypto_continuous_session_active():
    asyncio.run(trade_log.init_db())

    clock = get_market_clock()
    assert clock["is_open"] is True
    assert "24/7" in clock.get("reason", "")
