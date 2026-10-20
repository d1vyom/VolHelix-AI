import os
import sys
import pytest
from datetime import datetime

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.models.portfolio import PortfolioSnapshot
from backend.models.market import Regime, Trend, OptionLeg, StrategyType, MarketSignal, RiskFlags
from backend.models.trade import TradeProposal

@pytest.fixture
def base_portfolio():
    return PortfolioSnapshot(
        timestamp=datetime.now().isoformat(),
        equity=100000.0,
        buying_power=100000.0,
        daily_pnl=0.0,
        total_pnl=0.0,
        open_positions=0,
        net_delta=0.0,
        net_theta=0.0,
        net_vega=0.0,
        current_regime=Regime.NORMAL,
        exposures={}
    )

@pytest.fixture
def sample_legs():
    short_put = OptionLeg(
        action="SELL",
        contract_type="PUT",
        strike=500.0,
        expiry="2026-04-15",
        symbol="SPY260415P00500000",
        premium=4.50,
        delta=-0.25,
        gamma=0.02,
        theta=0.15,
        vega=-0.12,
        oi=500,
        bid=4.40,
        ask=4.60
    )
    long_put = OptionLeg(
        action="BUY",
        contract_type="PUT",
        strike=495.0,
        expiry="2026-04-15",
        symbol="SPY260415P00495000",
        premium=3.00,
        delta=0.15,
        gamma=-0.01,
        theta=-0.10,
        vega=0.08,
        oi=400,
        bid=2.90,
        ask=3.10
    )
    return short_put, long_put

@pytest.fixture
def sample_bull_put_proposal(sample_legs):
    short_put, long_put = sample_legs
    return TradeProposal(
        id="test-prop-001",
        underlying="SPY",
        symbol="SPY",
        strategy_type=StrategyType.MASTER_ORDER_FLOW,
        legs=[short_put, long_put],
        is_credit=True,
        net_premium=1.50,
        max_profit=1.50,
        max_loss=3.50,  # $350 risk per contract
        entry_price=500.0,
        qty=2.0,
        stop_loss=490.0,
        take_profit=520.0,
        breakevens=[498.50],
        net_delta=-0.10,
        net_theta=0.05,
        net_vega=-0.04,
        dte=30,
        ev=1.10,
        thesis="Bullish support bounce at 500"
    )

@pytest.fixture
def sample_crypto_proposal():
    return TradeProposal(
        id="test-crypto-001",
        underlying="BTCUSDT",
        symbol="BTCUSDT",
        strategy_type=StrategyType.MASTER_ORDER_FLOW,
        legs=[],
        is_credit=False,
        entry_price=60000.0,
        qty=0.01,  # $600 notional
        quote_qty=600.0,
        stop_loss=58800.0,
        take_profit=62400.0,
        max_profit=2400.0,
        max_loss=1200.0,
        breakevens=[60000.0],
        dte=0,
        ev=18.5,
        thesis="24/7 Parkinson volatility breakout with positive order book imbalance"
    )

@pytest.fixture
def sample_market_signal():
    return MarketSignal(
        timestamp=datetime.now().isoformat(),
        underlying="SPY",
        price=510.0,
        iv_current=0.16,
        iv_rank=0.35,
        iv_percentile=0.40,
        regime=Regime.NORMAL,
        trend=Trend.BULLISH,
        thesis="Steady uptrend with moderate volatility",
        confidence=0.85
    )

@pytest.fixture
def clean_risk_flags():
    return RiskFlags(
        events=[],
        risk_level="LOW",
        size_modifier=1.0
    )

# Safety must be installed during collection: auto_trader creates its singleton
# (and guardian) at import time, before function-scoped fixtures can run.
import asyncio
import importlib
import socket
import inspect
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import requests
import httpx
import sqlite3
from copy import deepcopy
from binance.client import Client as RealSDKClient


def _reject_network(*args, **kwargs):
    pytest.fail("Unexpected network access: supply an explicit test response")


class InertThread:
    """Exercise daemon state transitions without executing trading loops."""
    def __init__(self, *args, **kwargs):
        self.alive = False

    def start(self):
        self.alive = True

    def is_alive(self):
        return self.alive

    def join(self, *args, **kwargs):
        self.alive = False


_collection_patches = pytest.MonkeyPatch()
_collection_patches.setattr(requests.sessions.Session, "request", _reject_network)
_collection_patches.setattr(httpx.HTTPTransport, "handle_request", _reject_network)
_collection_patches.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _reject_network)
_collection_patches.setattr(socket, "create_connection", _reject_network)
_real_connect = socket.socket.connect


def _guard_connect(sock, address):
    # Windows asyncio creates a local socketpair; permit only that internal pair.
    if inspect.currentframe().f_back.f_code is getattr(socket.socketpair, "__code__", None):
        return _real_connect(sock, address)
    _reject_network()


_collection_patches.setattr(socket.socket, "connect", _guard_connect)
_collection_patches.setattr(socket.socket, "connect_ex", _reject_network)

# Logging normally posts back to the running application; unit tests have no server.
with patch("loguru.logger.add"):
    from backend.utils.logger import logger
logger.remove()
logger.add(sys.stderr, level="WARNING")

_active_temp_dir = None
_sqlite_connect = sqlite3.connect


def _temporary_sqlite_connect(database, *args, **kwargs):
    if _active_temp_dir is None or not Path(database).resolve().is_relative_to(_active_temp_dir):
        pytest.fail(f"Database outside test temporary directory: {database}")
    return _sqlite_connect(database, *args, **kwargs)


_collection_patches.setattr(sqlite3, "connect", _temporary_sqlite_connect)
exchange_module = importlib.import_module("backend.mcp.client")
_sdk_constructor = MagicMock(name="isolated Binance SDK", side_effect=_reject_network)
_collection_patches.setattr(exchange_module, "BinanceSDKClient", _sdk_constructor)

# Suppress only the import-time guardian start, then replace the auto-trader's
# module-local threading reference; HTTP/SQLite worker threads remain real.
with patch.object(threading.Thread, "start", lambda self: None):
    trader_module = importlib.import_module("backend.engine.auto_trader")
_collection_patches.setattr(trader_module, "threading", SimpleNamespace(
    Thread=InertThread, Event=threading.Event, current_thread=threading.current_thread,
))


def pytest_configure(config):
    (Path(PROJECT_ROOT) / "tmp").mkdir(exist_ok=True)
    config.option.basetemp = str(Path(PROJECT_ROOT) / "tmp" / "pytest")


def pytest_unconfigure(config):
    _collection_patches.undo()


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path):
    global _active_temp_dir
    _active_temp_dir = tmp_path.resolve()
    trades = importlib.import_module("backend.store.trade_log")
    postmortems = importlib.import_module("backend.store.postmortem_store")
    portfolio = importlib.import_module("backend.store.portfolio_store")
    routes = importlib.import_module("backend.api.routes")
    main = importlib.import_module("backend.main")
    from backend.config import settings
    from backend.store.flow_store import FlowStore

    monkeypatch.setattr(trades, "DB_PATH", str(tmp_path / "trades.db"))
    monkeypatch.setattr(postmortems, "DB_PATH", str(tmp_path / "postmortems.db"))
    flow_init = FlowStore.__init__

    def temporary_flow_init(self, db_path="flow.db"):
        flow_init(self, str(tmp_path / Path(db_path).name))

    monkeypatch.setattr(FlowStore, "__init__", temporary_flow_init)
    monkeypatch.setattr(main.hub.flow_store, "db_path", str(tmp_path / "flow.db"))
    for name in type(settings).model_fields:
        monkeypatch.setattr(settings, name, deepcopy(getattr(settings, name)))
    monkeypatch.setattr(settings, "BINANCE_API_KEY", "")
    monkeypatch.setattr(settings, "BINANCE_API_SECRET", "")
    # Restore settings even when an older test assigns to them directly.
    monkeypatch.setattr(settings, "FLOW_ENABLED", False)
    monkeypatch.setattr(settings, "FLOW_PERSIST_BARS", False)
    monkeypatch.setattr(main.hub, "start", AsyncMock())
    monkeypatch.setattr(main.hub, "stop", AsyncMock())
    monkeypatch.setattr(routes, "_binance_client", None)
    routes._invalidate_cache()
    exchange_module._CLIENT_CACHE.clear()
    trader_module.auto_trader.__dict__.clear()
    trader_module.AutoTrader._instance = trader_module.auto_trader
    trader_module.auto_trader.__init__()
    portfolio.portfolio_store.__init__()

    def sdk_factory(*args, **kwargs):
        sdk = MagicMock(spec=RealSDKClient)
        for name in dir(RealSDKClient):
            member = getattr(sdk, name, None)
            if isinstance(member, MagicMock) and not name.startswith("_"):
                member.side_effect = _reject_network
        sdk.get_server_time.side_effect = lambda: {"serverTime": int(time.time() * 1000)}
        return sdk

    _sdk_constructor.reset_mock()
    _sdk_constructor.side_effect = sdk_factory
    asyncio.run(trades.trade_log.init_db())
    asyncio.run(postmortems.postmortem_store.init_db())
    yield
    trader_module.auto_trader.stop()
    trader_module.auto_trader._guardian_stop_event.set()
    routes._invalidate_cache()
    exchange_module._CLIENT_CACHE.clear()
    _active_temp_dir = None


@pytest.fixture
def exchange_fixture(monkeypatch):
    client = exchange_module.BinanceClient()
    client.market_client.get_symbol_ticker.side_effect = None
    client.market_client.get_symbol_ticker.return_value = {"symbol": "SOLUSDT", "price": "150.00"}
    client.market_client.get_symbol_info.side_effect = None
    client.market_client.get_symbol_info.return_value = {'symbol':'SOLUSDT','baseAsset':'SOL','quoteAsset':'USDT','status':'TRADING','filters':[{'filterType':'LOT_SIZE','minQty':'0.00001','maxQty':'10000','stepSize':'0.00001'},{'filterType':'MIN_NOTIONAL','minNotional':'10'}]}
    client.trading_client.get_order.side_effect = RuntimeError('Order not found in explicit fixture')
    client.trading_client.get_account.side_effect = None
    client.trading_client.get_account.return_value = {'canTrade':True,'balances':[{'asset':'USDT','free':'10000','locked':'0'}]}
    def server_context(symbol):
        account=client.get_account()
        account['daily_pnl']=0
        return {'account':account,'score':.70,'is_valid':True,'side':'BUY','stop_loss':98,'take_profit':200}
    monkeypatch.setattr(client,'get_execution_context',server_context)
    return client
