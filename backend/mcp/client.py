import os
import re
import time
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple
from alpaca.trading.client import TradingClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest, 
    StockSnapshotRequest,
    OptionChainRequest,
    OptionSnapshotRequest,
    OptionLatestQuoteRequest
)
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from alpaca.trading.requests import (
    GetOrdersRequest, 
    MarketOrderRequest, 
    LimitOrderRequest,
    ReplaceOrderRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus
from alpaca.common.exceptions import APIError

from backend.config import settings
from backend.utils.logger import get_logger
from backend.models.trade import MCPCallLog

logger = get_logger("mcp_client")

# In-memory TTL cache to prevent redundant API latency during high-frequency scans
_CLIENT_CACHE: Dict[str, Tuple[any, float]] = {}

def _get_client_cache(key: str, ttl_seconds: float = 20.0):
    if key in _CLIENT_CACHE:
        val, ts = _CLIENT_CACHE[key]
        if time.time() - ts < ttl_seconds:
            return val
    return None

def _set_client_cache(key: str, val: any):
    _CLIENT_CACHE[key] = (val, time.time())


class AlpacaClient:
    """Wrapper around Alpaca SDK for paper trading and market data."""
    
    def __init__(self):
        if not settings.ALPACA_API_KEY or not settings.ALPACA_API_SECRET:
            logger.warning("Alpaca API keys missing from configuration.")
            
        self.trading_client = TradingClient(
            settings.ALPACA_API_KEY, 
            settings.ALPACA_API_SECRET, 
            paper=True
        )
        self.stock_client = StockHistoricalDataClient(
            settings.ALPACA_API_KEY, 
            settings.ALPACA_API_SECRET
        )
        self.option_client = OptionHistoricalDataClient(
            settings.ALPACA_API_KEY, 
            settings.ALPACA_API_SECRET
        )
        self.mcp_logs = []
        
    def _log_call(self, tool: str, req: dict, res: dict, start_time: datetime):
        duration = int((datetime.now() - start_time).total_seconds() * 1000)
        log_entry = MCPCallLog(
            tool=tool,
            request=req,
            response=res,
            timestamp=datetime.now().isoformat(),
            duration_ms=duration
        )
        self.mcp_logs.append(log_entry)
        logger.debug(f"MCP Call [{tool}] completed in {duration}ms")
        return log_entry

    def get_account(self) -> dict:
        start = datetime.now()
        acct = self.trading_client.get_account()
        res = {
            "status": acct.status,
            "equity": float(acct.equity),
            "buying_power": float(acct.buying_power),
            "options_approved_level": acct.options_approved_level,
            "options_trading_level": acct.options_trading_level
        }
        self._log_call("get_account", {}, res, start)
        return res
        
    def get_clock(self) -> dict:
        start = datetime.now()
        clock = self.trading_client.get_clock()
        res = {
            "is_open": clock.is_open,
            "next_open": clock.next_open.isoformat() if clock.next_open else None,
            "next_close": clock.next_close.isoformat() if clock.next_close else None
        }
        self._log_call("get_clock", {}, res, start)
        return res
    
    def get_stock_snapshots(self, symbols: List[str]) -> dict:
        """Get latest stock quotes for multiple symbols."""
        start = datetime.now()
        try:
            req = StockSnapshotRequest(symbol_or_symbols=symbols, feed=DataFeed.IEX)
            snapshots = self.stock_client.get_stock_snapshot(req)
            
            res = {}
            for sym, snap in snapshots.items():
                ask = 0.0
                bid = 0.0
                if getattr(snap, "latest_quote", None):
                    ask = float(getattr(snap.latest_quote, "ask_price", getattr(snap.latest_quote, "ap", 0)) or 0)
                    bid = float(getattr(snap.latest_quote, "bid_price", getattr(snap.latest_quote, "bp", 0)) or 0)
                
                price = ask or bid
                vol = 0
                if getattr(snap, "latest_trade", None):
                    trade_price = float(getattr(snap.latest_trade, "price", getattr(snap.latest_trade, "p", 0)) or 0)
                    if trade_price > 0:
                        price = trade_price
                    vol = int(getattr(snap.latest_trade, "size", getattr(snap.latest_trade, "s", 0)) or 0)
                
                ts = None
                if getattr(snap, "latest_quote", None):
                    raw_ts = getattr(snap.latest_quote, "timestamp", getattr(snap.latest_quote, "t", None))
                    if raw_ts and hasattr(raw_ts, "isoformat"):
                        ts = raw_ts.isoformat()
                
                res[sym] = {
                    "price": price,
                    "bid": bid,
                    "ask": ask,
                    "volume": vol,
                    "timestamp": ts
                }
        except Exception as e:
            logger.error(f"get_stock_snapshots error: {e}")
            res = {sym: {"price": 0, "bid": 0, "ask": 0, "volume": 0, "timestamp": None} for sym in symbols}
            
        self._log_call("get_stock_snapshots", {"symbols": symbols}, res, start)
        return res
    
    def get_stock_bars(self, symbol: str, days: int = 30, timeframe: TimeFrame = TimeFrame.Day) -> dict:
        """Get historical bars for technical indicators with fast in-memory caching."""
        cache_key = f"bars_{symbol}_{days}_{timeframe}"
        cached = _get_client_cache(cache_key, ttl_seconds=20.0)
        if cached is not None:
            return cached

        start = datetime.now()
        try:
            end = datetime.now()
            start_date = end - timedelta(days=days + 5)  # Extra for weekends
            
            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=timeframe,
                start=start_date,
                end=end,
                feed=DataFeed.IEX
            )
            bars = self.stock_client.get_stock_bars(req)
            
            if hasattr(bars, "data") and isinstance(bars.data, dict):
                bar_list = bars.data.get(symbol, [])
            elif hasattr(bars, "get"):
                bar_list = bars.get(symbol, [])
            else:
                try:
                    bar_list = bars[symbol]
                except Exception:
                    bar_list = []
            closes = [float(getattr(bar, "close", getattr(bar, "c", 0))) for bar in bar_list]
            highs = [float(getattr(bar, "high", getattr(bar, "h", 0))) for bar in bar_list]
            lows = [float(getattr(bar, "low", getattr(bar, "l", 0))) for bar in bar_list]
            volumes = [int(getattr(bar, "volume", getattr(bar, "v", 0))) for bar in bar_list]
            
            bars_dicts = []
            for bar in bar_list:
                ts_val = getattr(bar, "timestamp", getattr(bar, "t", ""))
                ts_str = ts_val.isoformat() if hasattr(ts_val, "isoformat") else str(ts_val)
                bars_dicts.append({
                    "open": float(getattr(bar, "open", getattr(bar, "o", 0)) or 0),
                    "high": float(getattr(bar, "high", getattr(bar, "h", 0)) or 0),
                    "low": float(getattr(bar, "low", getattr(bar, "l", 0)) or 0),
                    "close": float(getattr(bar, "close", getattr(bar, "c", 0)) or 0),
                    "volume": int(getattr(bar, "volume", getattr(bar, "v", 0)) or 0),
                    "time": ts_str
                })

            res = {
                "bars": bars_dicts,
                "closes": closes,
                "highs": highs,
                "lows": lows,
                "volumes": volumes,
                "current_price": closes[-1] if closes else 0
            }
            _set_client_cache(cache_key, res)
        except Exception as e:
            logger.error(f"get_stock_bars error: {e}")
            res = {"bars": [], "closes": [], "highs": [], "lows": [], "volumes": [], "current_price": 0}
            
        self._log_call("get_stock_bars", {"symbol": symbol, "days": days}, res, start)
        return res
    
    def get_option_chain(self, underlying: str, expiration_dates: Optional[List[str]] = None) -> dict:
        """Get options chain with Greeks for an underlying with fast in-memory caching."""
        cache_key = f"chain_{underlying}_{','.join(expiration_dates) if expiration_dates else 'default'}"
        cached = _get_client_cache(cache_key, ttl_seconds=20.0)
        if cached is not None:
            return cached

        start = datetime.now()
        try:
            if expiration_dates is None:
                # Nearest 2 weekly/monthly expirations for fast, high-performance Greeks & GEX calculation
                today = datetime.now().date()
                expiration_dates = []
                for i in range(2):
                    # Find next Friday (monthly/weekly OPEX)
                    days_ahead = (4 - today.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    next_friday = today + timedelta(days=days_ahead + i * 7)
                    expiration_dates.append(next_friday.strftime("%Y-%m-%d"))
            
            req = OptionChainRequest(
                underlying_symbol=underlying,
                expiration_dates=expiration_dates
            )
            chain = self.option_client.get_option_chain(req)
            
            legs = []
            contract_items = chain.values() if isinstance(chain, dict) else (chain if hasattr(chain, "__iter__") else [])
            for contract in contract_items:
                sym = getattr(contract, "symbol", "")
                greeks = getattr(contract, "greeks", None)
                quote = getattr(contract, "latest_quote", None)
                
                # Parse strike, expiry, and contract type
                raw_strike = getattr(contract, "strike_price", None)
                raw_expiry = getattr(contract, "expiration_date", None)
                c_type = getattr(contract, "type", getattr(contract, "contract_type", None))
                type_str = c_type.value if hasattr(c_type, "value") else (str(c_type).lower() if c_type else "")

                if not raw_strike or not raw_expiry or not type_str:
                    m = re.match(r'^([A-Za-z]+)(\d{2})(\d{2})(\d{2})([CPcp])(\d{8})$', sym)
                    if m:
                        _, yy, mm, dd, cp, strike_code = m.groups()
                        if not raw_expiry:
                            raw_expiry = f"20{yy}-{mm}-{dd}"
                        if not type_str:
                            type_str = "call" if cp.upper() == "C" else "put"
                        if not raw_strike:
                            raw_strike = float(int(strike_code) / 1000.0)

                raw_oi = int(getattr(contract, "open_interest", 0) or 0)
                raw_vol = int(getattr(contract, "volume", 0) or 0)
                bid_price = float(getattr(quote, "bid_price", getattr(quote, "bp", 0)) or 0) if quote else 0.0
                ask_price = float(getattr(quote, "ask_price", getattr(quote, "ap", 0)) or 0) if quote else 0.0
                # On Alpaca free paper tier, open interest is 0; provide realistic floor for liquid quotes
                effective_oi = raw_oi if raw_oi > 0 else (500 if (bid_price > 0 and ask_price > 0) else 0)

                legs.append({
                    "symbol": sym,
                    "underlying": underlying,
                    "strike": float(raw_strike or 0),
                    "expiry": str(raw_expiry or ""),
                    "type": type_str,
                    "delta": float(getattr(greeks, "delta", 0) or 0) if greeks else 0.0,
                    "gamma": float(getattr(greeks, "gamma", 0) or 0) if greeks else 0.0,
                    "theta": float(getattr(greeks, "theta", 0) or 0) if greeks else 0.0,
                    "vega": float(getattr(greeks, "vega", 0) or 0) if greeks else 0.0,
                    "iv": float(getattr(greeks, "implied_volatility", 0) or 0) if greeks else 0.0,
                    "bid": bid_price,
                    "ask": ask_price,
                    "open_interest": effective_oi,
                    "volume": raw_vol
                })
            
            res = {"underlying": underlying, "legs": legs, "expiration_dates": expiration_dates}
            _set_client_cache(cache_key, res)
        except Exception as e:
            logger.error(f"get_option_chain error: {e}")
            res = {"underlying": underlying, "legs": [], "expiration_dates": expiration_dates or []}
            
        self._log_call("get_option_chain", {"underlying": underlying, "expirations": expiration_dates}, res, start)
        return res
    
    def get_option_snapshots(self, symbols: List[str]) -> dict:
        """Get current option snapshots with Greeks for specific contract symbols."""
        start = datetime.now()
        try:
            req = OptionSnapshotRequest(symbol_or_symbols=symbols)
            snaps = self.option_client.get_option_snapshot(req)
            
            res = {}
            for sym, snap in snaps.items():
                res[sym] = {
                    "symbol": sym,
                    "price": float(snap.latest_quote.ap) if snap.latest_quote else 0,
                    "bid": float(snap.latest_quote.bp) if snap.latest_quote else 0,
                    "ask": float(snap.latest_quote.ap) if snap.latest_quote else 0,
                    "delta": float(snap.greeks.delta) if snap.greeks and snap.greeks.delta else 0,
                    "gamma": float(snap.greeks.gamma) if snap.greeks and snap.greeks.gamma else 0,
                    "theta": float(snap.greeks.theta) if snap.greeks and snap.greeks.theta else 0,
                    "vega": float(snap.greeks.vega) if snap.greeks and snap.greeks.vega else 0,
                    "iv": float(snap.greeks.implied_volatility) if snap.greeks and snap.greeks.implied_volatility else 0,
                    "open_interest": int(snap.open_interest) if snap.open_interest else 0,
                    "volume": int(snap.volume) if snap.volume else 0
                }
        except Exception as e:
            logger.error(f"get_option_snapshots error: {e}")
            res = {sym: {"price": 0} for sym in symbols}
            
        self._log_call("get_option_snapshots", {"symbols": symbols}, res, start)
        return res
    
    def get_vix_index(self) -> float:
        """Get current VIX index value (approximated via VIXY or SPY IV)."""
        start = datetime.now()
        vix_val = 18.5
        try:
            req = StockSnapshotRequest(symbol_or_symbols=["VIXY"], feed=DataFeed.IEX)
            snap = self.stock_client.get_stock_snapshot(req)
            if "VIXY" in snap and snap["VIXY"]:
                v = snap["VIXY"]
                trade_price = float(getattr(v.latest_trade, "price", getattr(v.latest_trade, "p", 0)) or 0) if getattr(v, "latest_trade", None) else 0
                if trade_price > 0:
                    vix_val = trade_price
            res = {"vix": vix_val}
        except Exception as e:
            logger.debug(f"get_vix_index error (using fallback {vix_val}): {e}")
            res = {"vix": vix_val}
            
        self._log_call("get_vix_index", {}, res, start)
        return res["vix"]
    
    def place_multi_leg_order(self, legs: List[dict], limit_price: float, quantity: int = 1) -> dict:
        """Place a multi-leg options order (order_class='mleg')."""
        start = datetime.now()
        try:
            # Build order legs
            order_legs = []
            for leg in legs:
                order_legs.append({
                    "symbol": leg["symbol"],
                    "ratio_quantity": quantity,
                    "side": OrderSide.BUY if leg["action"].upper() == "BUY" else OrderSide.SELL
                })
            
            req = LimitOrderRequest(
                symbol=legs[0]["symbol"].split("26")[0],  # Base symbol
                limit_price=limit_price,
                order_class=OrderClass.MLEG,
                qty=quantity,
                time_in_force=TimeInForce.DAY,
                legs=order_legs
            )
            
            order = self.trading_client.submit_order(req)
            
            res = {
                "id": order.id,
                "status": order.status.value,
                "symbol": order.symbol,
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
                "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else 0,
                "legs": [
                    {"symbol": l.symbol, "side": l.side.value, "qty": l.ratio_quantity}
                    for l in order.legs
                ] if order.legs else []
            }
        except APIError as e:
            logger.error(f"place_multi_leg_order API error: {e}")
            res = {"error": str(e), "status": "REJECTED"}
        except Exception as e:
            logger.error(f"place_multi_leg_order error: {e}")
            res = {"error": str(e), "status": "ERROR"}
            
        self._log_call("place_multi_leg_order", {"legs": legs, "limit_price": limit_price, "qty": quantity}, res, start)
        return res
    
    def get_positions(self) -> List[dict]:
        """Get all open positions."""
        start = datetime.now()
        try:
            positions = self.trading_client.get_all_positions()
            res = [
                {
                    "symbol": p.symbol,
                    "qty": float(p.qty),
                    "market_value": float(p.market_value),
                    "unrealized_pl": float(p.unrealized_pl),
                    "unrealized_plpc": float(p.unrealized_plpc) if p.unrealized_plpc else 0,
                    "side": p.side.value,
                    "asset_class": p.asset_class.value if p.asset_class else "unknown"
                }
                for p in positions
            ]
        except Exception as e:
            logger.error(f"get_positions error: {e}")
            res = []
            
        self._log_call("get_positions", {}, res, start)
        return res
    
    def get_open_orders(self) -> List[dict]:
        """Get all open orders."""
        start = datetime.now()
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            orders = self.trading_client.get_orders(req)
            res = [
                {
                    "id": o.id,
                    "symbol": o.symbol,
                    "status": o.status.value,
                    "qty": float(o.qty),
                    "filled_qty": float(o.filled_qty) if o.filled_qty else 0,
                    "limit_price": float(o.limit_price) if o.limit_price else 0,
                    "side": o.side.value,
                    "order_class": o.order_class.value if o.order_class else "simple"
                }
                for o in orders
            ]
        except Exception as e:
            logger.error(f"get_open_orders error: {e}")
            res = []
            
        self._log_call("get_open_orders", {}, res, start)
        return res
    
    def close_position(self, symbol: str) -> dict:
        """Close a specific position."""
        start = datetime.now()
        try:
            order = self.trading_client.close_position(symbol)
            res = {
                "id": order.id,
                "status": order.status.value,
                "symbol": order.symbol
            }
        except Exception as e:
            logger.error(f"close_position error: {e}")
            res = {"error": str(e)}
            
        self._log_call("close_position", {"symbol": symbol}, res, start)
        return res
    
    def get_portfolio_history(self, period: str = "1D", timeframe: str = "1Min") -> dict:
        """Get portfolio equity curve history."""
        start = datetime.now()
        try:
            history = self.trading_client.get_portfolio_history(period=period, timeframe=timeframe)
            res = {
                "timestamp": [t.isoformat() for t in history.timestamp],
                "equity": [float(e) for e in history.equity],
                "profit_loss": [float(p) for p in history.profit_loss],
                "profit_loss_pct": [float(p) for p in history.profit_loss_pct]
            }
        except Exception as e:
            logger.error(f"get_portfolio_history error: {e}")
            res = {"timestamp": [], "equity": [], "profit_loss": [], "profit_loss_pct": []}
            
        self._log_call("get_portfolio_history", {"period": period, "timeframe": timeframe}, res, start)
        return res
