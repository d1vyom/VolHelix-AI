import pytest
import asyncio
from backend.models.market import TradeStatus, StrategyType, OrderType
from backend.models.trade import TradeProposal, TradeRecord
from backend.store.trade_log import trade_log
from backend.utils.market_hours import get_market_clock, is_market_open, set_simulation_override
from fastapi.testclient import TestClient
from backend.main import fastapi_app

client = TestClient(fastapi_app)

def test_market_hours_and_simulation():
    asyncio.run(trade_log.init_db())

    # Test default clock info
    set_simulation_override(False)
    clock = get_market_clock()
    assert "is_open" in clock
    assert "current_time_et" in clock

    # Test override
    set_simulation_override(True)
    assert is_market_open() is True
    clock_overridden = get_market_clock()
    assert clock_overridden["is_open"] is True
    assert clock_overridden["simulation_active"] is True

    # Reset
    set_simulation_override(False)

def test_order_lifecycle_market_and_limit():
    asyncio.run(trade_log.init_db())
    set_simulation_override(True) # Allow trading for test

    # 1. Test Market Order submission via API
    res = client.post("/api/alpaca/order", json={
        "symbol": "SPY",
        "qty": 2,
        "side": "buy",
        "order_type": "market"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["status"] == "OPEN"
    assert data["order_type"] == "MARKET"
    assert data["qty"] == 2
    market_order_id = data["order_id"]

    # Verify market order appears in open positions
    open_trades = asyncio.run(trade_log.get_open_trades())
    open_ids = [t.trade_id for t in open_trades]
    assert market_order_id in open_ids

    # 2. Test Limit Order submission via API
    res_lmt = client.post("/api/alpaca/order", json={
        "symbol": "QQQ",
        "qty": 1,
        "side": "buy",
        "order_type": "limit",
        "limit_price": 485.50
    })
    assert res_lmt.status_code == 200
    lmt_data = res_lmt.json()
    assert lmt_data["success"] is True
    assert lmt_data["status"] == "PENDING"
    assert lmt_data["order_type"] == "LIMIT"
    assert lmt_data["limit_price"] == 485.50
    limit_order_id = lmt_data["order_id"]

    # Verify limit order appears in pending trades, NOT open trades
    pending_trades = asyncio.run(trade_log.get_pending_trades())
    pending_ids = [t.trade_id for t in pending_trades]
    assert limit_order_id in pending_ids

    open_trades_after = asyncio.run(trade_log.get_open_trades())
    assert limit_order_id not in [t.trade_id for t in open_trades_after]

    # 3. Test Fill Pending Limit Order via API
    fill_res = client.post(f"/api/trades/{limit_order_id}/fill", json={
        "fill_price": 485.00
    })
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
    close_res = client.post("/api/alpaca/close-position", json={
        "symbol": "SPY"
    })
    assert close_res.status_code == 200
    close_data = close_res.json()
    assert close_data["success"] is True
    assert close_data["status"] == "CLOSED"

    # Verify SPY is no longer in open trades, but in history trades
    open_final = asyncio.run(trade_log.get_open_trades())
    assert market_order_id not in [t.trade_id for t in open_final]

    history_trades = asyncio.run(trade_log.get_history_trades())
    history_ids = [t.trade_id for t in history_trades]
    assert market_order_id in history_ids

def test_market_closed_rejection():
    asyncio.run(trade_log.init_db())
    set_simulation_override(False)

    clock = get_market_clock()
    if not clock["is_open"]:
        # Submitting an order when market is closed should fail with 400
        res = client.post("/api/alpaca/order", json={
            "symbol": "AAPL",
            "qty": 1,
            "side": "buy",
            "order_type": "market"
        })
        assert res.status_code == 400
        assert "Market is closed" in res.json()["detail"]
