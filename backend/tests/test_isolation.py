"""Regression checks for the test harness safety boundary."""
import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest


def test_suite_uses_temporary_trade_store(tmp_path):
    import backend.store.trade_log as trades
    import backend.store.postmortem_store as postmortems

    assert Path(trades.DB_PATH).is_relative_to(tmp_path)
    assert Path(postmortems.DB_PATH).is_relative_to(tmp_path)
    asyncio.run(trades.trade_log.init_db())
    assert asyncio.run(trades.trade_log.get_all_trades()) == []
    assert asyncio.run(postmortems.postmortem_store.get_all()) == []
    from backend.store.flow_store import FlowStore
    assert Path(FlowStore().db_path).is_relative_to(tmp_path)


def test_exchange_fixture_never_contacts_network(exchange_fixture):
    from backend.mcp.client import BinanceClient
    from binance.client import Client

    # Even constructor ping/time synchronization must stay inside the fake SDK.
    with patch.object(Client, "_request", side_effect=AssertionError("real SDK invoked")) as request:
        client = BinanceClient()
        client.market_client = exchange_fixture.market_client
        assert client.get_price("SOLUSDT")["price"] == 150.0
        request.assert_not_called()



@pytest.mark.parametrize("transport", ["requests", "httpx", "socket", "sqlite"])
def test_unexpected_external_access_is_rejected(transport):
    import requests
    import httpx
    import socket
    import sqlite3

    with pytest.raises(pytest.fail.Exception):
        if transport == "requests":
            requests.get("https://api.binance.com/api/v3/ping")
        elif transport == "httpx":
            httpx.get("https://api.binance.com/api/v3/ping")
        elif transport == "socket":
            with socket.socket() as connection:
                connection.connect(("127.0.0.1", 8000))
        else:
            sqlite3.connect("application.db")
