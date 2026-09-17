# VolHelix AI — Backend Migration: Alpaca → Binance

> **Scope:** Every Python file in `backend/` that touches Alpaca.  
> **Library:** `python-binance` (pip install python-binance)  
> **Pattern:** Two client instances — one for REAL market data (production), one for PAPER trading (testnet).

---

## Table of Contents

1. [Dependencies (requirements.txt)](#1-dependencies)
2. [Config (config.py)](#2-config)
3. [Core Client (mcp/client.py)](#3-core-client)
4. [Engine: Auto Trader](#4-engine-auto-trader)
5. [Engine: Order Flow](#5-engine-order-flow)
6. [API Routes (api/routes.py)](#6-api-routes)
7. [Agents](#7-agents)
8. [Utilities](#8-utilities)
9. [Store Layer](#9-store-layer)

---

## 1. Dependencies

### File: `backend/requirements.txt`

**Remove these lines:**
```
alpaca-py
alpaca-mcp-server
```

**Add this line:**
```
python-binance
```

**Final `requirements.txt`:**
```
python-binance
google-genai
langchain-google-genai
langgraph
fastapi
uvicorn
python-socketio
pydantic
pydantic-settings
apscheduler
numpy
pandas
scipy
hmmlearn
loguru
python-dotenv
aiosqlite
httpx
pytest
```

---

## 2. Config

### File: `backend/config.py`

**Remove:**
```python
# Alpaca Configuration
ALPACA_API_KEY: str = ""
ALPACA_API_SECRET: str = ""
ALPACA_BASE_URL: str = "https://paper-api.alpaca.markets"
```

**Replace with:**
```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    # Binance Configuration
    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    BINANCE_BASE_URL: str = "https://testnet.binance.vision"
    BINANCE_USE_TESTNET: bool = True

    # LLM Configuration
    GOOGLE_API_KEY: str = ""
    LLM_MODEL: str = "gemini-3.6-flash"

    # Trading Configuration
    TRADING_INTERVAL_MINUTES: int = 5
    INITIAL_CAPITAL: float = 10000.0
    WATCHED_SYMBOLS_STR: str = Field(
        default="BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT",
        alias="WATCHED_SYMBOLS"
    )

    @property
    def WATCHED_SYMBOLS(self) -> list[str]:
        return [s.strip() for s in self.WATCHED_SYMBOLS_STR.split(",")]

    MAX_POSITION_PCT: float = 0.025
    MAX_DAILY_DRAWDOWN: float = 0.03

    # Server Configuration
    API_PORT: int = 8000
    DASHBOARD_PORT: int = 3000
    LOG_LEVEL: str = "INFO"

    # Crypto Market Constants (24/7 — no market hours restriction)
    MARKET_IS_ALWAYS_OPEN: bool = True

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
```

**Key changes:**
- `WATCHED_UNDERLYINGS` → `WATCHED_SYMBOLS` (alias still reads from env)
- Removed `MARKET_OPEN`, `MARKET_CLOSE`, `MARKET_TIMEZONE` (crypto is 24/7)
- Added `MARKET_IS_ALWAYS_OPEN = True`

---

## 3. Core Client

### File: `backend/mcp/client.py` — FULL REWRITE

This is the most critical file. It replaces `AlpacaClient` with `BinanceClient`.

**Architecture:** Two separate Binance client instances:
1. **`market_client`** — Connects to **production** Binance (`api.binance.com`) for real market data. NO API key needed for public endpoints.
2. **`trading_client`** — Connects to **testnet** Binance (`testnet.binance.vision`) for paper trading. REQUIRES testnet API key.

```python
"""
BinanceClient — Dual-mode client for VolHelix AI.

Market data  → Production Binance API (real prices)
Trading      → Testnet Binance API (paper trading, no real money)
"""
import time
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple

from binance.client import Client as BinanceSDKClient
from binance.exceptions import BinanceAPIException

from backend.config import settings
from backend.utils.logger import get_logger
from backend.models.trade import MCPCallLog

logger = get_logger("binance_client")

# In-memory TTL cache
_CLIENT_CACHE: Dict[str, Tuple[any, float]] = {}

def _get_client_cache(key: str, ttl_seconds: float = 10.0):
    if key in _CLIENT_CACHE:
        val, ts = _CLIENT_CACHE[key]
        if time.time() - ts < ttl_seconds:
            return val
    return None

def _set_client_cache(key: str, val: any):
    _CLIENT_CACHE[key] = (val, time.time())


class BinanceClient:
    """
    Wrapper around python-binance SDK.
    
    - market_client: production API for REAL market data (no API key for public endpoints)
    - trading_client: testnet API for PAPER trading (requires testnet API key)
    """

    def __init__(self):
        # Market data client — PRODUCTION (real prices, no key needed for public data)
        self.market_client = BinanceSDKClient("", "")  # No key for public endpoints

        # Trading client — TESTNET (paper trading)
        if not settings.BINANCE_API_KEY or not settings.BINANCE_API_SECRET:
            logger.warning("Binance testnet API keys missing. Trading will fail.")
        
        self.trading_client = BinanceSDKClient(
            settings.BINANCE_API_KEY,
            settings.BINANCE_API_SECRET,
            testnet=True
        )
        self.call_logs: List[MCPCallLog] = []

    def _log_call(self, tool: str, req: dict, res: dict, start_time: datetime) -> MCPCallLog:
        duration = int((datetime.now() - start_time).total_seconds() * 1000)
        log_entry = MCPCallLog(
            tool=tool,
            request=req,
            response=res if not isinstance(res, list) else {"count": len(res)},
            timestamp=datetime.now().isoformat(),
            duration_ms=duration
        )
        self.call_logs.append(log_entry)
        logger.debug(f"Binance [{tool}] completed in {duration}ms")
        return log_entry

    # ──────────────────────────────────────────────
    # ACCOUNT & BALANCE (Testnet)
    # ──────────────────────────────────────────────

    def get_account(self) -> dict:
        """Get testnet account info with balances."""
        start = datetime.now()
        try:
            account = self.trading_client.get_account()
            balances = {
                b["asset"]: {
                    "free": float(b["free"]),
                    "locked": float(b["locked"]),
                    "total": float(b["free"]) + float(b["locked"])
                }
                for b in account["balances"]
                if float(b["free"]) > 0 or float(b["locked"]) > 0
            }
            # Calculate total equity in USDT
            total_usdt = balances.get("USDT", {}).get("total", 0.0)
            res = {
                "status": account.get("status", "ACTIVE"),
                "equity": total_usdt,
                "buying_power": balances.get("USDT", {}).get("free", 0.0),
                "balances": balances,
                "can_trade": account.get("canTrade", True),
            }
        except BinanceAPIException as e:
            logger.error(f"get_account error: {e}")
            res = {
                "status": "ERROR",
                "equity": 0.0,
                "buying_power": 0.0,
                "balances": {},
                "error": str(e),
            }
        self._log_call("get_account", {}, res, start)
        return res

    def get_wallet_balances(self) -> List[dict]:
        """Get all non-zero balances from testnet."""
        start = datetime.now()
        try:
            account = self.trading_client.get_account()
            res = [
                {
                    "asset": b["asset"],
                    "free": float(b["free"]),
                    "locked": float(b["locked"]),
                    "total": float(b["free"]) + float(b["locked"])
                }
                for b in account["balances"]
                if float(b["free"]) > 0 or float(b["locked"]) > 0
            ]
        except Exception as e:
            logger.error(f"get_wallet_balances error: {e}")
            res = []
        self._log_call("get_wallet_balances", {}, {"count": len(res)}, start)
        return res

    # ──────────────────────────────────────────────
    # MARKET DATA (Production — real prices)
    # ──────────────────────────────────────────────

    def get_price(self, symbol: str) -> dict:
        """Get current price for a symbol (PRODUCTION data)."""
        cache_key = f"price_{symbol}"
        cached = _get_client_cache(cache_key, ttl_seconds=3.0)
        if cached:
            return cached
        
        start = datetime.now()
        try:
            ticker = self.market_client.get_symbol_ticker(symbol=symbol)
            res = {
                "symbol": ticker["symbol"],
                "price": float(ticker["price"]),
                "timestamp": datetime.now().isoformat()
            }
            _set_client_cache(cache_key, res)
        except Exception as e:
            logger.error(f"get_price error for {symbol}: {e}")
            res = {"symbol": symbol, "price": 0.0, "error": str(e)}
        self._log_call("get_price", {"symbol": symbol}, res, start)
        return res

    def get_24hr_ticker(self, symbol: str) -> dict:
        """Get 24hr ticker statistics (PRODUCTION data)."""
        cache_key = f"ticker24_{symbol}"
        cached = _get_client_cache(cache_key, ttl_seconds=5.0)
        if cached:
            return cached

        start = datetime.now()
        try:
            ticker = self.market_client.get_ticker(symbol=symbol)
            res = {
                "symbol": ticker["symbol"],
                "price_change": float(ticker["priceChange"]),
                "price_change_pct": float(ticker["priceChangePercent"]),
                "high": float(ticker["highPrice"]),
                "low": float(ticker["lowPrice"]),
                "volume": float(ticker["volume"]),
                "quote_volume": float(ticker["quoteVolume"]),
                "last_price": float(ticker["lastPrice"]),
                "bid": float(ticker["bidPrice"]),
                "ask": float(ticker["askPrice"]),
                "open": float(ticker["openPrice"]),
                "close": float(ticker["lastPrice"]),
                "count": int(ticker["count"]),
                "timestamp": datetime.now().isoformat()
            }
            _set_client_cache(cache_key, res)
        except Exception as e:
            logger.error(f"get_24hr_ticker error: {e}")
            res = {"symbol": symbol, "error": str(e)}
        self._log_call("get_24hr_ticker", {"symbol": symbol}, res, start)
        return res

    def get_all_tickers(self) -> List[dict]:
        """Get prices for all symbols (PRODUCTION data)."""
        cache_key = "all_tickers"
        cached = _get_client_cache(cache_key, ttl_seconds=5.0)
        if cached:
            return cached

        start = datetime.now()
        try:
            tickers = self.market_client.get_all_tickers()
            res = [
                {"symbol": t["symbol"], "price": float(t["price"])}
                for t in tickers
            ]
            _set_client_cache(cache_key, res)
        except Exception as e:
            logger.error(f"get_all_tickers error: {e}")
            res = []
        self._log_call("get_all_tickers", {}, {"count": len(res)}, start)
        return res

    def get_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> List[dict]:
        """
        Get candlestick/kline data (PRODUCTION data).
        
        Intervals: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M
        """
        cache_key = f"klines_{symbol}_{interval}_{limit}"
        cached = _get_client_cache(cache_key, ttl_seconds=15.0)
        if cached:
            return cached

        start = datetime.now()
        try:
            klines = self.market_client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            res = []
            for k in klines:
                res.append({
                    "open_time": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "close_time": k[6],
                    "quote_volume": float(k[7]),
                    "trades": int(k[8]),
                    "taker_buy_base": float(k[9]),
                    "taker_buy_quote": float(k[10]),
                })
            _set_client_cache(cache_key, res)
        except Exception as e:
            logger.error(f"get_klines error: {e}")
            res = []
        self._log_call("get_klines", {"symbol": symbol, "interval": interval, "limit": limit}, {"count": len(res)}, start)
        return res

    def get_order_book(self, symbol: str, limit: int = 20) -> dict:
        """Get order book depth (PRODUCTION data)."""
        start = datetime.now()
        try:
            depth = self.market_client.get_order_book(symbol=symbol, limit=limit)
            res = {
                "symbol": symbol,
                "bids": [[float(p), float(q)] for p, q in depth["bids"]],
                "asks": [[float(p), float(q)] for p, q in depth["asks"]],
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"get_order_book error: {e}")
            res = {"symbol": symbol, "bids": [], "asks": [], "error": str(e)}
        self._log_call("get_order_book", {"symbol": symbol, "limit": limit}, res, start)
        return res

    def get_recent_trades(self, symbol: str, limit: int = 50) -> List[dict]:
        """Get recent trades (PRODUCTION data)."""
        start = datetime.now()
        try:
            trades = self.market_client.get_recent_trades(symbol=symbol, limit=limit)
            res = [
                {
                    "id": t["id"],
                    "price": float(t["price"]),
                    "qty": float(t["qty"]),
                    "quote_qty": float(t["quoteQty"]),
                    "time": t["time"],
                    "is_buyer_maker": t["isBuyerMaker"],
                }
                for t in trades
            ]
        except Exception as e:
            logger.error(f"get_recent_trades error: {e}")
            res = []
        self._log_call("get_recent_trades", {"symbol": symbol}, {"count": len(res)}, start)
        return res

    def get_exchange_info(self, symbol: Optional[str] = None) -> dict:
        """Get exchange info for a symbol (filters, precision, limits)."""
        start = datetime.now()
        try:
            if symbol:
                info = self.market_client.get_symbol_info(symbol)
                res = {
                    "symbol": info["symbol"],
                    "base_asset": info["baseAsset"],
                    "quote_asset": info["quoteAsset"],
                    "status": info["status"],
                    "filters": info["filters"],
                    "base_precision": info["baseAssetPrecision"],
                    "quote_precision": info["quoteAssetPrecision"],
                }
            else:
                info = self.market_client.get_exchange_info()
                res = {
                    "timezone": info["timezone"],
                    "server_time": info["serverTime"],
                    "symbols_count": len(info["symbols"]),
                }
        except Exception as e:
            logger.error(f"get_exchange_info error: {e}")
            res = {"error": str(e)}
        self._log_call("get_exchange_info", {"symbol": symbol}, res, start)
        return res

    # ──────────────────────────────────────────────
    # TRADING (Testnet — paper trading)
    # ──────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        side: str,  # "BUY" or "SELL"
        order_type: str = "MARKET",  # "MARKET" or "LIMIT"
        quantity: Optional[float] = None,
        quote_quantity: Optional[float] = None,  # For MARKET buy with USDT amount
        price: Optional[float] = None,  # Required for LIMIT orders
        time_in_force: str = "GTC",
    ) -> dict:
        """Place an order on TESTNET (paper trading)."""
        start = datetime.now()
        try:
            params = {
                "symbol": symbol,
                "side": side.upper(),
                "type": order_type.upper(),
            }

            if order_type.upper() == "MARKET":
                if quote_quantity:
                    params["quoteOrderQty"] = quote_quantity
                elif quantity:
                    params["quantity"] = quantity
                else:
                    raise ValueError("Either quantity or quote_quantity required for MARKET order")
            elif order_type.upper() == "LIMIT":
                if not price:
                    raise ValueError("price required for LIMIT order")
                if not quantity:
                    raise ValueError("quantity required for LIMIT order")
                params["price"] = str(price)
                params["quantity"] = quantity
                params["timeInForce"] = time_in_force

            order = self.trading_client.create_order(**params)
            res = {
                "order_id": order["orderId"],
                "symbol": order["symbol"],
                "side": order["side"],
                "type": order["type"],
                "status": order["status"],
                "price": float(order.get("price", 0)),
                "orig_qty": float(order.get("origQty", 0)),
                "executed_qty": float(order.get("executedQty", 0)),
                "cummulative_quote_qty": float(order.get("cummulativeQuoteQty", 0)),
                "time_in_force": order.get("timeInForce", ""),
                "fills": order.get("fills", []),
            }
        except BinanceAPIException as e:
            logger.error(f"place_order API error: {e}")
            res = {"error": str(e), "status": "REJECTED", "code": e.code}
        except Exception as e:
            logger.error(f"place_order error: {e}")
            res = {"error": str(e), "status": "ERROR"}

        self._log_call("place_order", {
            "symbol": symbol, "side": side, "type": order_type,
            "qty": quantity, "quote_qty": quote_quantity, "price": price
        }, res, start)
        return res

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """Cancel a specific order on TESTNET."""
        start = datetime.now()
        try:
            result = self.trading_client.cancel_order(symbol=symbol, orderId=order_id)
            res = {
                "order_id": result["orderId"],
                "symbol": result["symbol"],
                "status": result["status"],
            }
        except BinanceAPIException as e:
            logger.error(f"cancel_order error: {e}")
            res = {"error": str(e), "code": e.code}
        self._log_call("cancel_order", {"symbol": symbol, "order_id": order_id}, res, start)
        return res

    def cancel_all_orders(self, symbol: str) -> dict:
        """Cancel all open orders for a symbol on TESTNET."""
        start = datetime.now()
        try:
            result = self.trading_client.cancel_order(symbol=symbol)
            res = {"symbol": symbol, "cancelled": True, "result": str(result)}
        except Exception as e:
            logger.error(f"cancel_all_orders error: {e}")
            res = {"symbol": symbol, "cancelled": False, "error": str(e)}
        self._log_call("cancel_all_orders", {"symbol": symbol}, res, start)
        return res

    def get_open_orders(self, symbol: Optional[str] = None) -> List[dict]:
        """Get all open orders on TESTNET."""
        start = datetime.now()
        try:
            params = {}
            if symbol:
                params["symbol"] = symbol
            orders = self.trading_client.get_open_orders(**params)
            res = [
                {
                    "order_id": o["orderId"],
                    "symbol": o["symbol"],
                    "side": o["side"],
                    "type": o["type"],
                    "status": o["status"],
                    "price": float(o.get("price", 0)),
                    "orig_qty": float(o.get("origQty", 0)),
                    "executed_qty": float(o.get("executedQty", 0)),
                    "time": o.get("time", 0),
                }
                for o in orders
            ]
        except Exception as e:
            logger.error(f"get_open_orders error: {e}")
            res = []
        self._log_call("get_open_orders", {"symbol": symbol}, {"count": len(res)}, start)
        return res

    def get_all_orders(self, symbol: str, limit: int = 50) -> List[dict]:
        """Get all orders (open, filled, cancelled) for a symbol on TESTNET."""
        start = datetime.now()
        try:
            orders = self.trading_client.get_all_orders(symbol=symbol, limit=limit)
            res = [
                {
                    "order_id": o["orderId"],
                    "symbol": o["symbol"],
                    "side": o["side"],
                    "type": o["type"],
                    "status": o["status"],
                    "price": float(o.get("price", 0)),
                    "orig_qty": float(o.get("origQty", 0)),
                    "executed_qty": float(o.get("executedQty", 0)),
                    "cummulative_quote_qty": float(o.get("cummulativeQuoteQty", 0)),
                    "time": o.get("time", 0),
                    "update_time": o.get("updateTime", 0),
                }
                for o in orders
            ]
        except Exception as e:
            logger.error(f"get_all_orders error: {e}")
            res = []
        self._log_call("get_all_orders", {"symbol": symbol, "limit": limit}, {"count": len(res)}, start)
        return res

    def get_my_trades(self, symbol: str, limit: int = 50) -> List[dict]:
        """Get trade history for a symbol on TESTNET."""
        start = datetime.now()
        try:
            trades = self.trading_client.get_my_trades(symbol=symbol, limit=limit)
            res = [
                {
                    "id": t["id"],
                    "order_id": t["orderId"],
                    "symbol": t["symbol"],
                    "price": float(t["price"]),
                    "qty": float(t["qty"]),
                    "quote_qty": float(t["quoteQty"]),
                    "commission": float(t["commission"]),
                    "commission_asset": t["commissionAsset"],
                    "time": t["time"],
                    "is_buyer": t["isBuyer"],
                    "is_maker": t["isMaker"],
                }
                for t in trades
            ]
        except Exception as e:
            logger.error(f"get_my_trades error: {e}")
            res = []
        self._log_call("get_my_trades", {"symbol": symbol}, {"count": len(res)}, start)
        return res

    # ──────────────────────────────────────────────
    # MULTI-SYMBOL HELPERS (used by dashboard)
    # ──────────────────────────────────────────────

    def get_watched_prices(self) -> dict:
        """Get latest prices for all watched symbols."""
        prices = {}
        for symbol in settings.WATCHED_SYMBOLS:
            data = self.get_price(symbol)
            prices[symbol] = data.get("price", 0.0)
        return prices

    def get_portfolio_value(self) -> dict:
        """Calculate total portfolio value in USDT."""
        account = self.get_account()
        balances = account.get("balances", {})
        total_value = 0.0
        holdings = []

        for asset, amounts in balances.items():
            if asset == "USDT":
                total_value += amounts["total"]
                holdings.append({
                    "asset": asset,
                    "quantity": amounts["total"],
                    "value_usdt": amounts["total"],
                    "price": 1.0
                })
            elif amounts["total"] > 0:
                symbol = f"{asset}USDT"
                try:
                    price_data = self.get_price(symbol)
                    price = price_data.get("price", 0.0)
                    value = amounts["total"] * price
                    total_value += value
                    holdings.append({
                        "asset": asset,
                        "quantity": amounts["total"],
                        "value_usdt": value,
                        "price": price
                    })
                except Exception:
                    pass

        return {
            "total_value_usdt": total_value,
            "holdings": holdings,
            "timestamp": datetime.now().isoformat()
        }
```

**Key design decisions:**
- `market_client` uses empty API key — public endpoints don't need authentication
- `trading_client` uses `testnet=True` — the `python-binance` library handles URL routing
- All market data methods use `self.market_client` (production, real data)
- All trading methods use `self.trading_client` (testnet, paper trading)
- Same caching pattern as the original AlpacaClient
- Same `_log_call` pattern for audit trail

---

## 4. Engine: Auto Trader

### File: `backend/engine/auto_trader.py`

**Remove all Alpaca imports:**
```python
# DELETE these lines:
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from alpaca.data.enums import DataFeed
from backend.mcp.client import AlpacaClient
```

**Replace with:**
```python
from backend.mcp.client import BinanceClient
```

**Replace `_get_trading_client` and `_get_stock_client` methods:**
```python
def _get_binance_client(self) -> BinanceClient:
    if not hasattr(self, '_binance_client') or self._binance_client is None:
        self._binance_client = BinanceClient()
    return self._binance_client
```

**Every call to `TradingClient(...)` or `StockHistoricalDataClient(...)` in auto_trader.py must be replaced with `self._get_binance_client()` and the corresponding BinanceClient methods.**

**Example replacements:**

| Old (Alpaca) | New (Binance) |
|---|---|
| `client.get_all_positions()` | `client.get_account()["balances"]` |
| `client.get_account()` | `client.get_account()` |
| `client.submit_order(MarketOrderRequest(...))` | `client.place_order(symbol, side, "MARKET", quantity=qty)` |
| `client.get_orders(GetOrdersRequest(status="all"))` | `client.get_all_orders(symbol)` |
| `sc.get_stock_latest_quote(...)` | `client.get_price(symbol)` |
| `client.cancel_order_by_id(order_id)` | `client.cancel_order(symbol, order_id)` |
| `client.close_position(symbol)` | `client.place_order(symbol, "SELL", "MARKET", quantity=position_qty)` |

> **IMPORTANT:** Binance does NOT have a `close_position` concept for spot. To close a position, you **sell** the asset. Calculate the quantity from the account balances.

---

## 5. Engine: Order Flow

### File: `backend/engine/order_flow.py`

This file uses Alpaca's `StockHistoricalDataClient` for OHLCV bars. Replace with BinanceClient's `get_klines()`.

**Replace:**
```python
from alpaca.data.historical import StockHistoricalDataClient
# ... any Alpaca data calls
```

**With:**
```python
from backend.mcp.client import BinanceClient

# Instead of Alpaca bars:
client = BinanceClient()
klines = client.get_klines(symbol="BTCUSDT", interval="1h", limit=100)

# klines already return: open, high, low, close, volume
closes = [k["close"] for k in klines]
highs = [k["high"] for k in klines]
lows = [k["low"] for k in klines]
volumes = [k["volume"] for k in klines]
```

---

## 6. API Routes

### File: `backend/api/routes.py`

This is the largest file (1229 lines) and has the most Alpaca dependencies.

**Rename ALL route prefixes:**
- `/api/alpaca/account` → `/api/exchange/account`
- `/api/alpaca/positions` → `/api/exchange/positions`
- `/api/alpaca/orders` → `/api/exchange/orders`
- `/api/alpaca/quote` → `/api/exchange/quote`
- `/api/alpaca/bars` → `/api/exchange/bars`
- `/api/alpaca/order` → `/api/exchange/order`
- `/api/alpaca/close-position` → `/api/exchange/close-position`
- `/api/alpaca/cancel-all` → `/api/exchange/cancel-all`

**Remove ALL Alpaca imports (lines ~242-248):**
```python
# DELETE:
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, CryptoLatestQuoteRequest, StockBarsRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed
```

**Replace with:**
```python
from backend.mcp.client import BinanceClient

_binance_client = None

def _get_binance_client() -> BinanceClient:
    global _binance_client
    if _binance_client is None:
        _binance_client = BinanceClient()
    return _binance_client
```

**Remove the three old helper functions:**
```python
# DELETE:
def _get_alpaca_trading_client(): ...
def _get_stock_client(): ...
def _get_crypto_client(): ...
```

### Route Replacement Examples

**Account route:**
```python
@router.get("/api/exchange/account")
def get_exchange_account():
    cached = _get_cached("account", ttl=3.0)
    if cached:
        return cached
    client = _get_binance_client()
    data = client.get_account()
    _set_cached("account", data)
    return data
```

**Quote route:**
```python
@router.get("/api/exchange/quote")
def get_exchange_quote(symbol: str = "BTCUSDT"):
    cache_key = f"quote_{symbol}"
    cached = _get_cached(cache_key, ttl=2.0)
    if cached:
        return cached
    client = _get_binance_client()
    ticker = client.get_24hr_ticker(symbol)
    res = {
        "symbol": symbol,
        "bid": ticker.get("bid", 0),
        "ask": ticker.get("ask", 0),
        "last": ticker.get("last_price", 0),
        "spread": round(ticker.get("ask", 0) - ticker.get("bid", 0), 4),
        "high": ticker.get("high", 0),
        "low": ticker.get("low", 0),
        "volume": ticker.get("volume", 0),
        "change_pct": ticker.get("price_change_pct", 0),
        "timestamp": ticker.get("timestamp", ""),
    }
    _set_cached(cache_key, res)
    return res
```

**Bars/Klines route:**
```python
@router.get("/api/exchange/bars")
def get_exchange_bars(symbol: str = "BTCUSDT", timeframe: str = "1h", limit: int = 100):
    cache_key = f"bars_{symbol}_{timeframe}_{limit}"
    cached = _get_cached(cache_key, ttl=15.0)
    if cached:
        return cached
    client = _get_binance_client()
    
    # Map timeframe strings
    tf_map = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1H": "1h", "1h": "1h", "4H": "4h", "4h": "4h",
        "1D": "1d", "1d": "1d", "1W": "1w", "1w": "1w",
    }
    interval = tf_map.get(timeframe, "1h")
    
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    
    result = []
    for k in klines:
        from datetime import datetime, timezone, timedelta
        ts = datetime.fromtimestamp(k["open_time"] / 1000, tz=timezone.utc)
        try:
            import zoneinfo
            ist = zoneinfo.ZoneInfo("Asia/Kolkata")
        except:
            ist = timezone(timedelta(hours=5, minutes=30))
        ts_ist = ts.astimezone(ist)

        if interval in ["1m", "5m", "15m", "30m"]:
            time_str = ts_ist.strftime("%H:%M")
        elif interval in ["1h", "2h", "4h"]:
            time_str = ts_ist.strftime("%m-%d %H:%M")
        else:
            time_str = ts_ist.strftime("%m-%d")

        result.append({
            "time": time_str,
            "raw_time": ts_ist.isoformat(),
            "open": k["open"],
            "high": k["high"],
            "low": k["low"],
            "close": k["close"],
            "volume": k["volume"],
        })
    
    if result:
        _set_cached(cache_key, result)
    return result
```

**Order submission route:**
```python
@router.post("/api/exchange/order")
async def submit_exchange_order(order_req: OrderSubmission):
    # Crypto markets are 24/7 — no market hours check needed
    client = _get_binance_client()
    
    if order_req.order_type.lower() == "limit":
        result = client.place_order(
            symbol=order_req.symbol,
            side=order_req.side.upper(),
            order_type="LIMIT",
            quantity=order_req.qty,
            price=order_req.limit_price,
        )
    else:
        result = client.place_order(
            symbol=order_req.symbol,
            side=order_req.side.upper(),
            order_type="MARKET",
            quantity=order_req.qty,
        )
    
    _invalidate_cache()
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return {
        "success": True,
        "order_id": str(result.get("order_id", "")),
        "symbol": result.get("symbol", order_req.symbol),
        "status": result.get("status", "UNKNOWN"),
        "order_type": order_req.order_type.upper(),
        "qty": order_req.qty,
        "side": order_req.side.upper(),
    }
```

---

## 7. Agents

### All Agent Files Need Import Updates

Every file in `backend/agents/` that imports from `backend.mcp.client` must change:

```python
# OLD:
from backend.mcp.client import AlpacaClient

# NEW:
from backend.mcp.client import BinanceClient
```

### File: `backend/agents/market_intel.py`

Replace Alpaca market data calls with BinanceClient:

| Old Call | New Call |
|---|---|
| `client.get_stock_snapshots(symbols)` | `client.get_price(symbol)` (loop per symbol) |
| `client.get_stock_bars(symbol, days=30)` | `client.get_klines(symbol, "1d", 30)` |
| `client.get_option_chain(underlying)` | **REMOVE** (no crypto options for now) |
| `client.get_vix_index()` | **REMOVE** or replace with crypto volatility calc |

### File: `backend/agents/executor.py`

Replace order execution:

| Old Call | New Call |
|---|---|
| `client.place_multi_leg_order(legs, price)` | `client.place_order(symbol, side, type, qty)` |
| `client.get_positions()` | `client.get_account()["balances"]` |
| `client.close_position(symbol)` | `client.place_order(symbol, "SELL", "MARKET", qty)` |
| `client.get_open_orders()` | `client.get_open_orders()` |

### File: `backend/agents/event_scanner.py`

Remove Alpaca news API calls. Replace with:
- Binance announcement scraping or a crypto news API
- Or simply remove the Alpaca-specific news logic and keep calendar events

### File: `backend/agents/orchestrator.py`

Update the orchestrator to:
1. Import `BinanceClient` instead of `AlpacaClient`
2. Pass crypto symbols instead of stock symbols
3. Remove options-specific pipeline steps (or adapt for spot trading)

---

## 8. Utilities

### File: `backend/utils/market_hours.py`

**Crypto trades 24/7.** Simplify this file:

```python
def check_market_open() -> dict:
    """Crypto markets are always open."""
    return {
        "is_open": True,
        "raw_is_open": True,
        "simulation_active": False,
        "current_time_et": datetime.now().isoformat(),
        "reason": "Crypto markets operate 24/7"
    }

def get_market_clock() -> dict:
    return check_market_open()
```

### File: `backend/utils/writeup_generator.py`

Replace all "Alpaca" text with "Binance". Replace "options" references with "crypto spot".

---

## 9. Store Layer

### File: `backend/store/portfolio_store.py`

This file references Alpaca. Update:
- Remove any `from alpaca...` imports
- The portfolio store tracks internal state — it mostly stays the same
- Update default watched symbols from stocks to crypto pairs

---

> **Document Version:** 1.0  
> **Created:** September 17, 2026  
> **Purpose:** Comprehensive backend migration guide for Gemini 3.8 Flash
