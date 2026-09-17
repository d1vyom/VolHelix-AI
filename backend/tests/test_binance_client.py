import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from backend.mcp.client import BinanceClient

def test_binance_client_initialization():
    client = BinanceClient()
    assert client.market_client is not None
    assert client.trading_client is not None
    assert hasattr(client, "call_logs")
    assert hasattr(client, "timestamp_offset") or hasattr(client.trading_client, "timestamp_offset")

def test_binance_client_time_sync():
    client = BinanceClient()
    # Mock get_server_time to return 1000ms ahead
    now_ms = int(datetime.now().timestamp() * 1000)
    with patch.object(client.trading_client, "get_server_time", return_value={"serverTime": now_ms + 1500}):
        client._sync_time()
        assert client.trading_client.timestamp_offset == pytest.approx(1500, abs=500)

def test_binance_client_get_price():
    client = BinanceClient()
    with patch.object(client.market_client, "get_symbol_ticker", return_value={"symbol": "BTCUSDT", "price": "65432.10"}):
        res = client.get_price("BTCUSDT")
        assert res["symbol"] == "BTCUSDT"
        assert res["price"] == 65432.10

def test_binance_client_get_ticker_24hr():
    client = BinanceClient()
    mock_data = {
        "symbol": "ETHUSDT",
        "lastPrice": "3450.00",
        "priceChange": "50.00",
        "priceChangePercent": "1.47",
        "highPrice": "3500.00",
        "lowPrice": "3400.00",
        "volume": "15000.0"
    }
    with patch.object(client.market_client, "get_ticker", return_value=mock_data):
        res = client.get_ticker_24hr("ETHUSDT")
        assert res["symbol"] == "ETHUSDT"
        assert res["price"] == 3450.00
        assert res["price_change_percent"] == 1.47
        assert res["high"] == 3500.00
        assert res["low"] == 3400.00

def test_binance_client_get_order_book():
    client = BinanceClient()
    mock_depth = {
        "bids": [["60000.00", "1.50000"]],
        "asks": [["60010.00", "2.00000"]]
    }
    with patch.object(client.market_client, "get_order_book", return_value=mock_depth):
        res = client.get_order_book("BTCUSDT", limit=5)
        assert res["symbol"] == "BTCUSDT"
        assert res["spread"] == pytest.approx(10.00, 0.01)
        assert len(res["bids"]) == 1
        assert len(res["asks"]) == 1

def test_binance_client_get_account_filters_non_zero():
    client = BinanceClient()
    mock_account = {
        "balances": [
            {"asset": "USDT", "free": "10000.00", "locked": "0.00"},
            {"asset": "BTC", "free": "0.05", "locked": "0.00"},
            {"asset": "DOGE", "free": "0.00", "locked": "0.00"},
        ]
    }
    with patch.object(client.trading_client, "get_account", return_value=mock_account):
        acct = client.get_account()
        assert acct["status"] == "ACTIVE"
        assert "USDT" in acct["balances"]
        assert "BTC" in acct["balances"]
        assert "DOGE" not in acct["balances"]
        assert acct["balances"]["BTC"]["total"] == 0.05

def test_binance_client_audit_logging():
    client = BinanceClient()
    start_len = len(client.call_logs)
    
    with patch.object(client.market_client, "get_symbol_ticker", return_value={"symbol": "SOLUSDT", "price": "145.50"}):
        client.get_price("SOLUSDT")
        
    assert len(client.call_logs) == start_len + 1
    logs = client.get_audit_logs(limit=10)
    assert len(logs) >= 1
    assert logs[0]["tool"] == "get_price"
    assert logs[0]["duration_ms"] >= 0
