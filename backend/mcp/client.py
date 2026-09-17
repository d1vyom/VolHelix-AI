"""
BinanceClient — Dual-mode client for VolHelix AI.

Market data  → Production Binance API (api.binance.com, real prices, no key needed)
Trading      → Testnet Binance API (testnet.binance.vision, paper trading, no real money)
"""
import time
from datetime import datetime
from typing import List, Optional, Dict, Tuple, Any

from binance.client import Client as BinanceSDKClient
from binance.exceptions import BinanceAPIException

from backend.config import settings
from backend.utils.logger import get_logger
from backend.models.trade import MCPCallLog

logger = get_logger("binance_client")

# In-memory TTL cache
_CLIENT_CACHE: Dict[str, Tuple[Any, float]] = {}


def _get_client_cache(key: str, ttl_seconds: float = 10.0) -> Optional[Any]:
    if key in _CLIENT_CACHE:
        val, ts = _CLIENT_CACHE[key]
        if time.time() - ts < ttl_seconds:
            return val
    return None


def _set_client_cache(key: str, val: Any) -> None:
    _CLIENT_CACHE[key] = (val, time.time())


class BinanceClient:
    """
    Dual-mode client for Binance.
    
    - market_client: Production API for real market data (public endpoints, no auth required).
    - trading_client: Testnet API for paper trading (requires testnet API key & secret).
    """

    def __init__(self):
        # Production market client (real market data)
        self.market_client = BinanceSDKClient("", "")

        # Testnet paper trading client
        if not settings.BINANCE_API_KEY or not settings.BINANCE_API_SECRET:
            logger.warning("Binance testnet API keys missing. Paper trading operations will fail.")

        self.trading_client = BinanceSDKClient(
            settings.BINANCE_API_KEY,
            settings.BINANCE_API_SECRET,
            testnet=True
        )
        self._sync_time()

        self.call_logs: List[MCPCallLog] = []
        # Backward compatibility attribute alias
        self.mcp_logs = self.call_logs

    def _sync_time(self) -> None:
        """Synchronize system clock difference with Binance server time to avoid -1021 errors."""
        try:
            server_time = self.trading_client.get_server_time()
            self.trading_client.timestamp_offset = server_time["serverTime"] - int(time.time() * 1000)
            logger.info(f"Binance testnet time synced. Offset: {self.trading_client.timestamp_offset}ms")
        except Exception as e:
            logger.warning(f"Could not calculate Binance timestamp offset: {e}")

    def _log_call(self, tool: str, req: dict, res: Any, start_time: datetime) -> MCPCallLog:
        duration = int((datetime.now() - start_time).total_seconds() * 1000)
        if isinstance(res, dict):
            res_dict = res
        elif isinstance(res, list):
            res_dict = {"count": len(res)}
        else:
            res_dict = {"data": str(res)}

        log_entry = MCPCallLog(
            tool=tool,
            request=req,
            response=res_dict,
            timestamp=datetime.now().isoformat(),
            duration_ms=duration
        )
        self.call_logs.append(log_entry)
        logger.debug(f"Binance [{tool}] completed in {duration}ms")
        return log_entry

    # ──────────────────────────────────────────────
    # ACCOUNT & BALANCE (Testnet Paper Trading)
    # ──────────────────────────────────────────────

    def get_account(self) -> dict:
        """Get testnet account information with non-zero balances and USDT equity."""
        start = datetime.now()
        try:
            account = self.trading_client.get_account()
            balances = {
                b["asset"]: {
                    "free": float(b["free"]),
                    "locked": float(b["locked"]),
                    "total": float(b["free"]) + float(b["locked"])
                }
                for b in account.get("balances", [])
                if float(b["free"]) > 0 or float(b["locked"]) > 0
            }
            total_usdt = balances.get("USDT", {}).get("total", 0.0)
            res = {
                "status": "ACTIVE",
                "equity": total_usdt,
                "buying_power": balances.get("USDT", {}).get("free", 0.0),
                "balances": balances,
                "can_trade": account.get("canTrade", True),
            }
        except BinanceAPIException as e:
            if e.code == -1021:
                self._sync_time()
                try:
                    return self.get_account()
                except Exception:
                    pass
            logger.error(f"get_account Binance API error: {e}")
            res = {
                "status": "ERROR",
                "equity": 0.0,
                "buying_power": 0.0,
                "balances": {},
                "can_trade": False,
                "error": str(e),
            }
        except Exception as e:
            logger.error(f"get_account error: {e}")
            res = {
                "status": "ERROR",
                "equity": 0.0,
                "buying_power": 0.0,
                "balances": {},
                "can_trade": False,
                "error": str(e),
            }
        self._log_call("get_account", {}, res, start)
        return res

    def get_wallet_balances(self) -> List[dict]:
        """Get all non-zero asset balances from testnet."""
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
                for b in account.get("balances", [])
                if float(b["free"]) > 0 or float(b["locked"]) > 0
            ]
        except BinanceAPIException as e:
            if e.code == -1021:
                self._sync_time()
                try:
                    return self.get_wallet_balances()
                except Exception:
                    pass
            logger.error(f"get_wallet_balances error: {e}")
            res = []
        except Exception as e:
            logger.error(f"get_wallet_balances error: {e}")
            res = []
        self._log_call("get_wallet_balances", {}, res, start)
        return res

    def get_positions(self) -> List[dict]:
        """
        Get crypto spot holdings as positions.
        Returns all valid non-USDT assets with positive balance and current USDT value.
        """
        start = datetime.now()
        positions = []
        try:
            acct = self.get_account()
            balances = acct.get("balances", {})
            tickers_map = {t["symbol"]: t["price"] for t in self.get_all_tickers()}

            for asset, amounts in balances.items():
                if asset != "USDT" and amounts["total"] > 0:
                    symbol = f"{asset}USDT"
                    curr_price = tickers_map.get(symbol, 0.0)
                    if curr_price > 0:
                        market_value = amounts["total"] * curr_price
                        # Only track watched symbols to avoid arbitrary testnet airdrop/gift balances
                        if symbol in settings.WATCHED_SYMBOLS:
                            positions.append({
                                "symbol": symbol,
                                "asset": asset,
                                "qty": amounts["total"],
                                "free_qty": amounts["free"],
                                "locked_qty": amounts["locked"],
                                "current_price": curr_price,
                                "market_value": round(market_value, 2),
                            })
        except Exception as e:
            logger.error(f"get_positions error: {e}")
        self._log_call("get_positions", {}, positions, start)
        return positions

    # ──────────────────────────────────────────────
    # MARKET DATA (Production — Real Prices)
    # ──────────────────────────────────────────────

    def get_price(self, symbol: str) -> dict:
        """Get current live price for a symbol (Production)."""
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
        """Get 24hr statistics for a symbol (Production)."""
        cache_key = f"ticker24_{symbol}"
        cached = _get_client_cache(cache_key, ttl_seconds=5.0)
        if cached:
            return cached

        start = datetime.now()
        try:
            ticker = self.market_client.get_ticker(symbol=symbol)
            res = {
                "symbol": ticker["symbol"],
                "price_change": float(ticker.get("priceChange", 0)),
                "price_change_pct": float(ticker.get("priceChangePercent", 0)),
                "high": float(ticker.get("highPrice", 0)),
                "low": float(ticker.get("lowPrice", 0)),
                "volume": float(ticker.get("volume", 0)),
                "quote_volume": float(ticker.get("quoteVolume", 0)),
                "last_price": float(ticker.get("lastPrice", 0)),
                "bid": float(ticker.get("bidPrice", 0)),
                "ask": float(ticker.get("askPrice", 0)),
                "open": float(ticker.get("openPrice", 0)),
                "close": float(ticker.get("lastPrice", 0)),
                "count": int(ticker.get("count", 0)),
                "timestamp": datetime.now().isoformat()
            }
            _set_client_cache(cache_key, res)
        except Exception as e:
            logger.error(f"get_24hr_ticker error for {symbol}: {e}")
            res = {"symbol": symbol, "error": str(e)}
        self._log_call("get_24hr_ticker", {"symbol": symbol}, res, start)
        return res

    def get_all_tickers(self) -> List[dict]:
        """Get prices for all active symbols (Production)."""
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
        self._log_call("get_all_tickers", {}, res, start)
        return res

    def get_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> List[dict]:
        """
        Get candlestick/kline bars (Production).
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
            logger.error(f"get_klines error for {symbol}: {e}")
            res = []
        self._log_call("get_klines", {"symbol": symbol, "interval": interval, "limit": limit}, res, start)
        return res

    def get_order_book(self, symbol: str, limit: int = 20) -> dict:
        """Get order book depth (Production)."""
        start = datetime.now()
        try:
            depth = self.market_client.get_order_book(symbol=symbol, limit=limit)
            res = {
                "symbol": symbol,
                "bids": [[float(p), float(q)] for p, q in depth.get("bids", [])],
                "asks": [[float(p), float(q)] for p, q in depth.get("asks", [])],
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"get_order_book error for {symbol}: {e}")
            res = {"symbol": symbol, "bids": [], "asks": [], "error": str(e)}
        self._log_call("get_order_book", {"symbol": symbol, "limit": limit}, res, start)
        return res

    def get_recent_trades(self, symbol: str, limit: int = 50) -> List[dict]:
        """Get recent trades for a symbol (Production)."""
        start = datetime.now()
        try:
            trades = self.market_client.get_recent_trades(symbol=symbol, limit=limit)
            res = [
                {
                    "id": t["id"],
                    "price": float(t["price"]),
                    "qty": float(t["qty"]),
                    "quote_qty": float(t.get("quoteQty", 0)),
                    "time": t["time"],
                    "is_buyer_maker": t.get("isBuyerMaker", False),
                }
                for t in trades
            ]
        except Exception as e:
            logger.error(f"get_recent_trades error for {symbol}: {e}")
            res = []
        self._log_call("get_recent_trades", {"symbol": symbol, "limit": limit}, res, start)
        return res

    def get_exchange_info(self, symbol: Optional[str] = None) -> dict:
        """Get exchange info and filters (Production)."""
        start = datetime.now()
        try:
            if symbol:
                info = self.market_client.get_symbol_info(symbol)
                if not info:
                    return {"error": f"Symbol {symbol} not found"}
                res = {
                    "symbol": info["symbol"],
                    "base_asset": info["baseAsset"],
                    "quote_asset": info["quoteAsset"],
                    "status": info["status"],
                    "filters": info.get("filters", []),
                    "base_precision": info.get("baseAssetPrecision", 8),
                    "quote_precision": info.get("quoteAssetPrecision", 8),
                }
            else:
                info = self.market_client.get_exchange_info()
                res = {
                    "timezone": info.get("timezone", "UTC"),
                    "server_time": info.get("serverTime", 0),
                    "symbols_count": len(info.get("symbols", [])),
                }
        except Exception as e:
            logger.error(f"get_exchange_info error: {e}")
            res = {"error": str(e)}
        self._log_call("get_exchange_info", {"symbol": symbol}, res, start)
        return res

    # ──────────────────────────────────────────────
    # TRADING (Testnet Paper Trading)
    # ──────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        side: str,  # "BUY" or "SELL"
        order_type: str = "MARKET",  # "MARKET" or "LIMIT"
        quantity: Optional[float] = None,
        quote_quantity: Optional[float] = None,
        price: Optional[float] = None,
        time_in_force: str = "GTC",
    ) -> dict:
        """Place an order on Binance Spot Testnet."""
        start = datetime.now()
        try:
            params: Dict[str, Any] = {
                "symbol": symbol.upper(),
                "side": side.upper(),
                "type": order_type.upper(),
            }

            if order_type.upper() == "MARKET":
                if quote_quantity:
                    params["quoteOrderQty"] = quote_quantity
                elif quantity:
                    params["quantity"] = quantity
                else:
                    raise ValueError("Either quantity or quote_quantity is required for MARKET order")
            elif order_type.upper() == "LIMIT":
                if not price:
                    raise ValueError("price is required for LIMIT order")
                if not quantity:
                    raise ValueError("quantity is required for LIMIT order")
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
            if e.code == -1021:
                self._sync_time()
                try:
                    return self.place_order(
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        quantity=quantity,
                        quote_quantity=quote_quantity,
                        price=price,
                        time_in_force=time_in_force
                    )
                except Exception:
                    pass
            logger.error(f"place_order API error: {e}")
            res = {"error": str(e), "status": "REJECTED", "code": e.code}
        except Exception as e:
            logger.error(f"place_order error: {e}")
            res = {"error": str(e), "status": "ERROR"}

        self._log_call(
            "place_order",
            {"symbol": symbol, "side": side, "type": order_type, "qty": quantity, "quote_qty": quote_quantity, "price": price},
            res,
            start
        )
        return res

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """Cancel an open order on Testnet."""
        start = datetime.now()
        try:
            result = self.trading_client.cancel_order(symbol=symbol.upper(), orderId=order_id)
            res = {
                "order_id": result.get("orderId", order_id),
                "symbol": result.get("symbol", symbol),
                "status": result.get("status", "CANCELED"),
            }
        except BinanceAPIException as e:
            if e.code == -1021:
                self._sync_time()
                try:
                    return self.cancel_order(symbol=symbol, order_id=order_id)
                except Exception:
                    pass
            logger.error(f"cancel_order API error: {e}")
            res = {"error": str(e), "code": e.code}
        except Exception as e:
            logger.error(f"cancel_order error: {e}")
            res = {"error": str(e)}
        self._log_call("cancel_order", {"symbol": symbol, "order_id": order_id}, res, start)
        return res

    def cancel_all_orders(self, symbol: str) -> dict:
        """Cancel all open orders for a symbol on Testnet."""
        start = datetime.now()
        try:
            open_orders = self.get_open_orders(symbol=symbol)
            cancelled_ids = []
            for ord_item in open_orders:
                oid = ord_item.get("order_id")
                if oid:
                    try:
                        self.trading_client.cancel_order(symbol=symbol.upper(), orderId=oid)
                        cancelled_ids.append(oid)
                    except Exception as ce:
                        logger.warning(f"Failed to cancel order {oid}: {ce}")
            res = {"symbol": symbol, "cancelled": True, "cancelled_order_ids": cancelled_ids}
        except Exception as e:
            logger.error(f"cancel_all_orders error: {e}")
            res = {"symbol": symbol, "cancelled": False, "error": str(e)}
        self._log_call("cancel_all_orders", {"symbol": symbol}, res, start)
        return res

    def get_open_orders(self, symbol: Optional[str] = None) -> List[dict]:
        """Get all open orders on Testnet."""
        start = datetime.now()
        try:
            params = {}
            if symbol:
                params["symbol"] = symbol.upper()
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
        except BinanceAPIException as e:
            if e.code == -1021:
                self._sync_time()
                try:
                    return self.get_open_orders(symbol=symbol)
                except Exception:
                    pass
            logger.error(f"get_open_orders error: {e}")
            res = []
        except Exception as e:
            logger.error(f"get_open_orders error: {e}")
            res = []
        self._log_call("get_open_orders", {"symbol": symbol}, res, start)
        return res

    def get_all_orders(self, symbol: str, limit: int = 50) -> List[dict]:
        """Get all orders (open, filled, cancelled) for a symbol on Testnet."""
        start = datetime.now()
        try:
            orders = self.trading_client.get_all_orders(symbol=symbol.upper(), limit=limit)
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
        except BinanceAPIException as e:
            if e.code == -1021:
                self._sync_time()
                try:
                    return self.get_all_orders(symbol=symbol, limit=limit)
                except Exception:
                    pass
            logger.error(f"get_all_orders error for {symbol}: {e}")
            res = []
        except Exception as e:
            logger.error(f"get_all_orders error for {symbol}: {e}")
            res = []
        self._log_call("get_all_orders", {"symbol": symbol, "limit": limit}, res, start)
        return res

    def get_my_trades(self, symbol: str, limit: int = 50) -> List[dict]:
        """Get trade execution history for a symbol on Testnet."""
        start = datetime.now()
        try:
            trades = self.trading_client.get_my_trades(symbol=symbol.upper(), limit=limit)
            res = [
                {
                    "id": t["id"],
                    "order_id": t["orderId"],
                    "symbol": t["symbol"],
                    "price": float(t["price"]),
                    "qty": float(t["qty"]),
                    "quote_qty": float(t.get("quoteQty", 0)),
                    "commission": float(t.get("commission", 0)),
                    "commission_asset": t.get("commissionAsset", ""),
                    "time": t.get("time", 0),
                    "is_buyer": t.get("isBuyer", False),
                    "is_maker": t.get("isMaker", False),
                }
                for t in trades
            ]
        except BinanceAPIException as e:
            if e.code == -1021:
                self._sync_time()
                try:
                    return self.get_my_trades(symbol=symbol, limit=limit)
                except Exception:
                    pass
            logger.error(f"get_my_trades error for {symbol}: {e}")
            res = []
        except Exception as e:
            logger.error(f"get_my_trades error for {symbol}: {e}")
            res = []
        self._log_call("get_my_trades", {"symbol": symbol, "limit": limit}, res, start)
        return res

    # ──────────────────────────────────────────────
    # MULTI-SYMBOL & HELPERS
    # ──────────────────────────────────────────────

    def get_watched_prices(self) -> dict:
        """Get latest prices for all watched symbols."""
        prices = {}
        for symbol in settings.WATCHED_SYMBOLS:
            data = self.get_price(symbol)
            prices[symbol] = data.get("price", 0.0)
        return prices

    def get_portfolio_value(self) -> dict:
        """Calculate total portfolio value in USDT across all holdings."""
        account = self.get_account()
        balances = account.get("balances", {})
        total_value = 0.0
        holdings = []
        tickers_map = {t["symbol"]: t["price"] for t in self.get_all_tickers()}

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
                price = tickers_map.get(symbol, 0.0)
                if price > 0:
                    value = amounts["total"] * price
                    if value >= 0.10 or symbol in settings.WATCHED_SYMBOLS:
                        total_value += value
                        holdings.append({
                            "asset": asset,
                            "quantity": amounts["total"],
                            "value_usdt": round(value, 2),
                            "price": price
                        })

        return {
            "total_value_usdt": round(total_value, 2),
            "holdings": holdings,
            "timestamp": datetime.now().isoformat()
        }

    def get_clock(self) -> dict:
        """Crypto markets operate 24/7."""
        return {
            "is_open": True,
            "raw_is_open": True,
            "simulation_active": False,
            "current_time_et": datetime.now().isoformat(),
            "reason": "Crypto markets operate 24/7"
        }

    # Backward compatibility helper wrappers
    def get_stock_latest_quote(self, symbol: str) -> dict:
        p = self.get_price(symbol)
        return {"symbol": symbol, "price": p.get("price", 0.0), "bid": p.get("price", 0.0), "ask": p.get("price", 0.0)}

    def get_stock_bars(self, symbol: str, days: int = 30) -> List[dict]:
        return self.get_klines(symbol=symbol, interval="1d", limit=days)

    def get_stock_snapshots(self, symbols: List[str]) -> dict:
        return {s: self.get_price(s) for s in symbols}


# Backward-compatible class alias during progressive migration
AlpacaClient = BinanceClient
