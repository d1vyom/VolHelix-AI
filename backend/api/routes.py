import time
import uuid
import threading
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

try:
    import zoneinfo
    IST_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")
except Exception:
    IST_TZ = timezone(timedelta(hours=5, minutes=30))

from backend.config import settings
from backend.models.trade import TradeRecord, TradeProposal
from backend.models.market import OptionLeg, StrategyType, TradeStatus
from backend.exchange.models import Market
from backend.exchange.registry import get_exchange_client
from backend.exchange.lifecycle import execute_entry, reconcile_trade, cancel_trade_order, close_trade_position
from backend.store.portfolio_store import portfolio_store
from backend.store.trade_log import trade_log
from backend.store.postmortem_store import postmortem_store
from backend.store.regime_history import get_regime_history
from backend.engine.iv_calculator import load_iv_history
from backend.engine.order_flow import (
    analyze_order_flow,
    calculate_master_strategy_tp_sl,
    evaluate_master_strategy_setup
)
from backend.engine.auto_trader import auto_trader
from backend.mcp.client import BinanceClient
from backend.utils.logger import get_logger
from backend.utils.market_hours import get_market_clock, check_market_open
from backend.utils.calendar import get_upcoming_events

logger = get_logger("routes")

router = APIRouter()

# -------------------------------------------------------------
# In-Memory Cache
# -------------------------------------------------------------
_CACHE = {}

def _get_cached(key: str, ttl: float = 3.0):
    entry = _CACHE.get(key)
    if entry and (time.time() - entry["time"] < ttl):
        return entry["data"]
    return None

def _set_cached(key: str, data):
    _CACHE[key] = {"time": time.time(), "data": data}

def _invalidate_cache(prefixes: Optional[List[str]] = None):
    global _CACHE
    if prefixes:
        for k in list(_CACHE.keys()):
            if any(k.startswith(p) for p in prefixes):
                _CACHE.pop(k, None)
    else:
        volatile = ["positions", "orders", "account", "history", "quote"]
        for k in list(_CACHE.keys()):
            if any(k.startswith(p) for p in volatile):
                _CACHE.pop(k, None)

# Client Singleton
_binance_client: Optional[BinanceClient] = None

def _get_binance_client() -> BinanceClient:
    global _binance_client
    if _binance_client is None:
        _binance_client = BinanceClient()
    return _binance_client

# Backward-compatibility aliases for engine/tests
def _get_alpaca_trading_client() -> BinanceClient:
    logger.warning("Alpaca routes and client aliases are deprecated. Use /api/exchange/* endpoints.")
    return _get_binance_client()

def _get_stock_client() -> BinanceClient:
    return _get_binance_client()

def _get_crypto_client() -> BinanceClient:
    return _get_binance_client()

def _normalize_symbol(symbol: str) -> str:
    """Map legacy equity tickers and formatting to Binance crypto pairs."""
    s = (symbol or "BTCUSDT").upper().replace("/", "").replace("-", "").replace(" ", "").strip()
    if s in ("SPY", "QQQ", "AAPL", "NVDA", "TSLA", "BTC", "BTCUSD"):
        return "BTCUSDT"
    if s in ("ETH", "ETHUSD"):
        return "ETHUSDT"
    if s in ("SOL", "SOLUSD"):
        return "SOLUSDT"
    if s in ("BNB", "BNBUSD"):
        return "BNBUSDT"
    if s in ("XRP", "XRPUSD"):
        return "XRPUSDT"
    if s.endswith("USDT"):
        return s
    return f"{s}USDT"


# -------------------------------------------------------------
# Core System & Health Endpoints
# -------------------------------------------------------------

@router.get("/api/health")
def health_check():
    return {"status": "ok", "service": "volhelix-ai", "exchange": "binance", "mode": "24/7-crypto"}


@router.get("/api/portfolio")
def get_portfolio():
    return portfolio_store.get_snapshot().model_dump()


@router.get("/api/trades")
async def get_trades(market: Market = 'spot'):
    # The ledger records acknowledgements. Reading history must not invent fills
    # or infer realized PnL from unrelated exchange SELL orders.
    return [t.model_dump() for t in await trade_log.get_all_trades() if t.market==market]


@router.get("/api/positions")
async def get_positions(market: Market = 'spot'):
    trades = await trade_log.get_open_trades()
    return [t.model_dump() for t in trades if t.market==market]


@router.get("/api/trades/history")
async def get_trade_history(market: Market = 'spot'):
    trades = await trade_log.get_all_trades()
    closed = [t.model_dump() for t in trades if t.market==market and t.status in (TradeStatus.CLOSED, TradeStatus.STOPPED_OUT, TradeStatus.TAKE_PROFIT, TradeStatus.CANCELLED)]
    return closed


@router.get("/api/trades/pending")
async def get_pending_trades(market: Market = 'spot'):
    trades = await trade_log.get_pending_trades()
    return [t.model_dump() for t in trades if t.market==market]


@router.get("/api/market-status")
def get_market_status():
    """Return the 24/7 crypto session clock. Execution is never gated on market hours."""
    return get_market_clock()


@router.get("/api/audit")
def get_audit_trail():
    client = _get_binance_client()
    logs = client.get_audit_logs(limit=50)
    return {
        "mcp_calls": logs,
        "summary": {
            "total_calls": len(logs),
            "errors": sum(1 for l in logs if l.get("status") == "ERROR"),
            "success": sum(1 for l in logs if l.get("status") == "SUCCESS"),
            "service": "binance_mcp_client"
        }
    }


@router.get("/api/signals")
def get_signals():
    """Return live 24h market signals for every watched symbol."""
    client = _get_binance_client()
    signals = []
    for s in settings.WATCHED_SYMBOLS:
        ticker = client.get_24hr_ticker(s) or {}
        change = float(ticker.get("price_change_pct", 0.0) or 0.0)
        signals.append({
            "symbol": s,
            "current_price": float(ticker.get("last_price", 0.0) or 0.0),
            "change_24h": change,
            "volume_24h": float(ticker.get("quote_volume", 0.0) or 0.0),
            "high_24h": float(ticker.get("high", 0.0) or 0.0),
            "low_24h": float(ticker.get("low", 0.0) or 0.0),
            "trend": "BULLISH" if change >= 0 else "BEARISH",
            "timestamp": datetime.now().isoformat()
        })
    return signals


@router.get("/api/regime")
def get_regime():
    snapshot = portfolio_store.get_snapshot()
    return {
        "current_regime": getattr(snapshot.current_regime, "value", str(snapshot.current_regime)),
        "history": get_regime_history(limit=30),
        "timestamp": datetime.now().isoformat()
    }


@router.get("/api/iv-data")
def get_iv_data(symbol: str = "BTCUSDT"):
    clean_sym = _normalize_symbol(symbol)
    history = load_iv_history(clean_sym)
    return {
        "symbol": clean_sym,
        "history": history
    }


@router.get("/api/postmortems")
async def get_postmortems():
    return await postmortem_store.get_all()


class InternalLogRequest(BaseModel):
    agent: str
    message: str
    confidence: Optional[float] = 1.0

@router.post("/api/internal/log")
async def internal_log(req: InternalLogRequest):
    try:
        from backend.api.websocket import sio
        await sio.emit("reasoning_event", {
            "agent": req.agent,
            "message": req.message,
            "confidence": req.confidence or 1.0,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.debug(f"Failed to emit reasoning_event: {e}")
    return {"status": "logged"}


# -------------------------------------------------------------
# Exchange & Binance Live Trading Endpoints
# -------------------------------------------------------------

@router.get("/api/exchange/account")
@router.get("/api/alpaca/account")
def get_exchange_account():
    cached = _get_cached("account", ttl=2.0)
    if cached:
        return cached

    client = _get_binance_client()
    try:
        acc = client.get_account()
        data = {
            "equity": float(acc.get("equity", settings.INITIAL_CAPITAL)),
            "buying_power": float(acc.get("buying_power", settings.INITIAL_CAPITAL)),
            "cash": float(acc.get("cash", settings.INITIAL_CAPITAL)),
            "portfolio_value": float(acc.get("equity", settings.INITIAL_CAPITAL)),
            "status": "ACTIVE",
            "currency": "USDT",
            "balances": acc.get("balances", {})
        }
        _set_cached("account", data)
        return data
    except Exception as e:
        return {
            "equity": settings.INITIAL_CAPITAL,
            "buying_power": settings.INITIAL_CAPITAL,
            "cash": settings.INITIAL_CAPITAL,
            "portfolio_value": settings.INITIAL_CAPITAL,
            "status": "ACTIVE",
            "currency": "USDT",
            "error": str(e)
        }


@router.get("/api/exchange/positions")
@router.get("/api/alpaca/positions")
async def get_exchange_positions(market: Market = 'spot'):
    from backend.exchange.lifecycle import position_snapshot
    return (await position_snapshot(market))['positions']


@router.get("/api/exchange/orders")
@router.get("/api/alpaca/orders")
async def get_exchange_orders(limit: int = 50, market: Market = 'spot'):
    from backend.exchange.lifecycle import order_snapshot
    return (await order_snapshot(market))[:max(1,min(limit,200))]


@router.delete("/api/exchange/orders/{order_id}")
@router.delete("/api/alpaca/orders/{order_id}")
async def cancel_exchange_order(order_id: str, symbol: Optional[str] = None, market: Market = 'spot'):
    trade=await trade_log.find_trade(order_id,market,symbol)
    if not trade:
        raise HTTPException(status_code=404,detail='Recorded order not found in selected market')
    try:
        client=await asyncio.to_thread(get_exchange_client,market)
        trade=await cancel_trade_order(trade,client=client)
    except Exception as exc:
        raise HTTPException(status_code=502,detail=str(exc)) from exc
    _invalidate_cache()
    return {'success':True,'order_id':order_id,'trade_id':trade.trade_id,'market':market,
            'status':trade.status.value,'exchange_status':trade.exchange_status,'qty':trade.proposal.qty}


@router.post("/api/exchange/cancel-all")
@router.post("/api/alpaca/cancel-all")
async def cancel_all_exchange_orders(market: Market = 'spot'):
    pending=[t for t in await trade_log.get_pending_trades() if t.market==market]
    results=[]; errors=[]
    for trade in pending:
        try:
            results.append(await cancel_exchange_order(trade.trade_id,trade.proposal.symbol,market))
        except HTTPException as exc:
            errors.append({'trade_id':trade.trade_id,'error':exc.detail})
    from backend.store import order_intents
    for intent in await asyncio.to_thread(order_intents.pending,market):
        if intent['status'] in ('UNKNOWN','DISPATCHING'):
            errors.append({'intent_id':intent['identity'],'error':'Exchange outcome unresolved; reservation retained'})
    return {'success':not errors,'cancelled':len(results),'errors':errors,'market':market}


@router.get("/api/exchange/quote")
@router.get("/api/alpaca/quote")
def get_exchange_quote(symbol: str = "BTCUSDT"):
    clean_sym = _normalize_symbol(symbol)
    cache_key = f"quote_{clean_sym}"
    cached = _get_cached(cache_key, ttl=1.5)
    if cached is not None:
        return cached

    client = _get_binance_client()
    try:
        ticker = client.get_24hr_ticker(clean_sym)
        bid = float(ticker.get("bid", 0.0))
        ask = float(ticker.get("ask", 0.0))
        last = float(ticker.get("last", ask or bid or 75000.0))
        res = {
            "symbol": clean_sym,
            "bid": bid if bid > 0 else round(last * 0.9999, 2),
            "ask": ask if ask > 0 else round(last * 1.0001, 2),
            "last": last,
            "high_24h": float(ticker.get("high", last * 1.02)),
            "low_24h": float(ticker.get("low", last * 0.98)),
            "volume_24h": float(ticker.get("volume", 1500.0)),
            "price_change_24h": float(ticker.get("price_change", 0.0)),
            "price_change_percent_24h": float(ticker.get("price_change_percent", 0.0)),
            "spread": round(ask - bid, 4) if (ask > 0 and bid > 0) else 0.50,
            "timestamp": datetime.now().isoformat()
        }
        _set_cached(cache_key, res)
        return res
    except Exception as e:
        fallback = 76600.0 if "BTC" in clean_sym else 2460.0
        return {
            "symbol": clean_sym,
            "bid": fallback - 0.5,
            "ask": fallback + 0.5,
            "last": fallback,
            "spread": 1.0,
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }


@router.get("/api/exchange/bars")
@router.get("/api/alpaca/bars")
def get_exchange_bars(symbol: str = "BTCUSDT", timeframe: str = "1H", limit: int = 80):
    clean_sym = _normalize_symbol(symbol)
    tf_clean = timeframe.strip()
    cache_key = f"bars_{clean_sym}_{tf_clean}_{limit}"
    cached = _get_cached(cache_key, ttl=15.0)
    if cached is not None:
        return cached

    tf_map = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1H": "1h",
        "1h": "1h",
        "4H": "4h",
        "4h": "4h",
        "1D": "1d",
        "1d": "1d"
    }
    binance_tf = tf_map.get(tf_clean, "1h")
    client = _get_binance_client()

    try:
        klines = client.get_klines(clean_sym, interval=binance_tf, limit=limit)
        result = []
        for k in klines:
            ts_ms = k["open_time"]
            dt_utc = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            dt_ist = dt_utc.astimezone(IST_TZ)

            if tf_clean in ["1m", "5m", "15m"]:
                time_str = dt_ist.strftime("%H:%M")
            elif tf_clean in ["1H", "1h", "4H", "4h"]:
                time_str = dt_ist.strftime("%m-%d %H:%M")
            else:
                time_str = dt_ist.strftime("%m-%d")

            result.append({
                "time": time_str,
                "raw_time": dt_ist.isoformat(),
                "open": float(k["open"]),
                "high": float(k["high"]),
                "low": float(k["low"]),
                "close": float(k["close"]),
                "volume": float(k["volume"])
            })

        if result:
            _set_cached(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"get_exchange_bars error: {e}")
        raise HTTPException(status_code=503, detail="Market data unavailable")


from backend.exchange.schemas import OrderRequest
from backend.exchange.execution import submit_order, OrderExecutionError, MarketDataUnavailable

# Preserve the existing import and route contract.
OrderSubmission = OrderRequest


@router.post("/api/exchange/order")
@router.post("/api/alpaca/order")
async def submit_exchange_order(order_req: OrderSubmission):
    clean_sym = _normalize_symbol(order_req.symbol)
    request = order_req.model_copy(update={"symbol": clean_sym})
    try:
        result,trade = await execute_entry(request,client=await asyncio.to_thread(get_exchange_client,request.market))
    except MarketDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OrderExecutionError as exc:
        raise HTTPException(status_code=409 if 'conflict' in str(exc) else 502, detail=str(exc)) from exc
    status=trade.status
    filled=result.exchange_status=='FILLED'
    tp_price=trade.take_profit_price
    sl_price=trade.stop_loss_price
    _invalidate_cache()
    try:
        from backend.api.websocket import sio
        await sio.emit("reasoning_event", {
            "agent": "Exchange", "message": f"Testnet order {result.order_id}: {result.exchange_status}",
            "confidence": 1.0,
        })
        if filled:
            await sio.emit("trade_executed", {"trade_id": trade.trade_id, "market":request.market, "symbol": clean_sym,
                                            "status": status.value, "entry_price": result.entry_price})
    except Exception:
        pass
    return {"success": True, **result.model_dump(), "trade_id":trade.trade_id, "symbol": clean_sym, "market":request.market,
            "status": status.value, "order_type": request.order_type,
            "limit_price": request.limit_price, "qty": result.executed_qty,
            "side": request.side, "take_profit_price": tp_price, "stop_loss_price": sl_price,
            "message": f"Binance Testnet: {result.exchange_status}"}


class FillPendingTradeRequest(BaseModel):
    fill_price: Optional[float] = None

@router.post("/api/trades/{trade_id}/fill")
async def fill_pending_trade_endpoint(trade_id: str, req: Optional[FillPendingTradeRequest] = None, market: Market = 'spot'):
    trade=await trade_log.find_trade(trade_id,market)
    if not trade:
        raise HTTPException(status_code=404,detail='Trade not found in selected market')
    if req and req.fill_price is not None:
        raise HTTPException(status_code=400,detail='Manual fills are forbidden; reconcile exchange state without fill_price')
    try:
        client=await asyncio.to_thread(get_exchange_client,market)
        trade=await reconcile_trade(trade,client=client)
    except OrderExecutionError as exc:
        raise HTTPException(status_code=502,detail=str(exc)) from exc
    _invalidate_cache()
    return {'success':True,'trade_id':trade.trade_id,'market':market,'status':trade.status.value,
            'exchange_status':trade.exchange_status,'fill_price':trade.entry_price,'qty':trade.proposal.qty}


class ClosePositionRequest(BaseModel):
    symbol: str
    market: Market = 'spot'
    trade_id: Optional[str] = None


@router.post("/api/exchange/close-position")
@router.post("/api/alpaca/close-position")
async def close_exchange_position(req: ClosePositionRequest):
    symbol=_normalize_symbol(req.symbol)
    trades=[t for t in await trade_log.get_open_trades() if t.market==req.market and t.proposal.symbol==symbol and (not req.trade_id or t.trade_id==req.trade_id)]
    if not trades:
        raise HTTPException(status_code=404,detail='No recorded exposure in selected market')
    try:
        client=await asyncio.to_thread(get_exchange_client,req.market)
        closed=[]
        for trade in trades:
            closed.append(await close_trade_position(trade,client=client))
    except Exception as exc:
        raise HTTPException(status_code=502,detail=str(exc)) from exc
    _invalidate_cache()
    return {'success':True,'market':req.market,'symbol':symbol,
            'status':'CLOSED' if all(t.status==TradeStatus.CLOSED for t in closed) else 'OPEN',
            'qty':sum(t.proposal.qty for t in closed),'exit_price':closed[-1].exit_price,
            'realized_pnl':sum(t.realized_pnl for t in closed),'trades':[t.model_dump() for t in closed]}


class BotExecutionRequest(BaseModel):
    market: Market = 'spot'
    qty: float = 0.001
    client_order_id: Optional[str] = None
    symbol: str = "BTCUSDT"
    strategy: str = "MASTER_ORDER_FLOW"
    risk_fraction: float = 0.8
    take_profit_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None

@router.post("/api/bot/execute-trade")
async def execute_bot_trade(req: BotExecutionRequest):
    # The shared server risk gate supplies fresh confluence and account checks.
    result=await submit_exchange_order(OrderRequest(market=req.market,symbol=req.symbol,
        quote_quantity=200 if req.market=='spot' else None,qty=req.qty,
        client_order_id=req.client_order_id))
    return {**result,'strategy':req.strategy,'decision':'ACKNOWLEDGED',
            'binance_order_id':result['order_id']}


@router.get("/api/analytics/order-flow")
def get_order_flow_analytics(symbol: str = "BTCUSDT"):
    clean_sym = _normalize_symbol(symbol)
    cache_key = f"order_flow_{clean_sym}"
    cached = _get_cached(cache_key, ttl=30.0)
    if cached is not None:
        return cached

    try:
        client = _get_binance_client()
        klines = client.get_klines(clean_sym, interval="1h", limit=48)
        # Adapt klines to simple bar objects
        bars = [
            {
                "open": float(k["open"]),
                "high": float(k["high"]),
                "low": float(k["low"]),
                "close": float(k["close"]),
                "volume": float(k["volume"]),
                "timestamp": datetime.fromtimestamp(k["open_time"] / 1000)
            }
            for k in klines
        ]
        order_flow = analyze_order_flow(clean_sym, bars)
        res = {
            "success": True,
            "order_flow": order_flow.model_dump()
        }
        _set_cached(cache_key, res)
        return res
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/api/exchange/clock")
def get_exchange_clock():
    return get_market_clock()


# -------------------------------------------------------------
# Auto-Trading Control Routes
# -------------------------------------------------------------

@router.get("/api/bot/auto-trading/status")
def get_auto_trading_status():
    return auto_trader.status()


class AutoTradingStartRequest(BaseModel):
    interval: int = 30

@router.post("/api/bot/auto-trading/start")
def start_auto_trading(req: Optional[AutoTradingStartRequest] = None):
    interval = req.interval if req else 30
    return auto_trader.start(interval=interval)


@router.post("/api/bot/auto-trading/stop")
def stop_auto_trading():
    return auto_trader.stop()


class TriggerCycleRequest(BaseModel):
    symbol: Optional[str] = None

@router.post("/api/bot/auto-trading/trigger-cycle")
def trigger_auto_trading_cycle(req: Optional[TriggerCycleRequest] = None, symbol: Optional[str] = None):
    target_sym = None
    if req and req.symbol:
        target_sym = _normalize_symbol(req.symbol)
    elif symbol:
        target_sym = _normalize_symbol(symbol)
    return auto_trader.trigger_cycle(symbol=target_sym)
from backend.api.market_routes import router as market_router
router.include_router(market_router)
