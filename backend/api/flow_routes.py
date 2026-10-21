from collections import OrderedDict
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Literal
import time

from backend.config import settings
from backend.marketdata.hub import hub, get_hub
from backend.api.flow_schemas import StatusResponse, SubscribeRequest, UnsubscribeRequest
from backend.api.routes import _normalize_symbol

router = APIRouter(tags=["order-flow"])
_FLOW_CACHE: OrderedDict[str, tuple[float, dict]] = OrderedDict()


def _get_cached(key: str, ttl: float):
    entry = _FLOW_CACHE.get(key)
    if entry and time.monotonic() - entry[0] < ttl:
        return entry[1]
    return None


def _set_cached(key: str, data: dict) -> None:
    _FLOW_CACHE[key] = (time.monotonic(), data)
    _FLOW_CACHE.move_to_end(key)
    while len(_FLOW_CACHE) > 64:
        _FLOW_CACHE.popitem(last=False)


def _market_hub(market: str):
    return hub if market == "spot" else get_hub(market)


def check_flow_enabled():
    if not settings.FLOW_ENABLED:
        raise HTTPException(status_code=503, detail={"enabled": False, "reason": "Order flow engine is disabled via configuration"})

@router.get("/api/flow/status")
def get_flow_status(market: Literal["spot", "futures"] = "spot"):
    selected = _market_hub(market)
    if not settings.FLOW_ENABLED:
        return StatusResponse(enabled=False, market=market, reason="Order flow disabled")
    return StatusResponse(
        enabled=True,
        market=market,
        symbols=list(selected.books.keys()),
        health=selected.health()
    )

@router.get("/api/flow/footprint")
def get_footprint(
    symbol: str, 
    interval: str = "1m", 
    limit: int = Query(default=60, ge=1, le=240),
    tick_group: Optional[float] = Query(default=None, gt=0, allow_inf_nan=False),
    market: Literal["spot", "futures"] = "spot"
):
    check_flow_enabled()
    selected = _market_hub(market)
    sym = _normalize_symbol(symbol)
    state = selected.get_state(sym)
    if not state:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False, "market": market}
    
    cache_key = f"flow_{market}_{selected.cache_generation}_footprint_{sym}_{interval}_{limit}_{tick_group}"
    cached = _get_cached(cache_key, ttl=1.0)
    if cached: return cached
    
    bars_list = selected.get_footprint_bars(sym, interval, limit=limit)
    
    # tick_group is an override, but if it differs from what footprint.py uses we would need to re-aggregate.
    # Snapshots report their actual engine grouping, including the display row cap.
    actual_tick_group = bars_list[0].tick_group if bars_list else (tick_group or 10.0)

    res = {
        "symbol": sym, "market": market,
        "interval": interval,
        "tick_group": actual_tick_group,
        "bars": [b.model_dump() for b in bars_list]
    }
    _set_cached(cache_key, res)
    return res

@router.get("/api/flow/dom")
def get_dom(symbol: str, levels: int = Query(default=20, ge=1, le=100), tick_group: Optional[float] = Query(default=None, gt=0, allow_inf_nan=False), market: Literal["spot", "futures"] = "spot"):
    check_flow_enabled()
    selected = _market_hub(market)
    sym = _normalize_symbol(symbol)
    state = selected.get_state(sym)
    if not state:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False, "market": market}
        
    cache_key = f"flow_{market}_{selected.cache_generation}_dom_{sym}_{levels}_{tick_group}"
    cached = _get_cached(cache_key, ttl=0.25)
    if cached: return cached
    
    analytics = selected.get_dom(sym, levels)
    if analytics is None:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False, "market": market}

    res = analytics.model_dump()
    res["market"] = market
    res["server_ts"] = int(time.time() * 1000)
    _set_cached(cache_key, res)
    return res

@router.get("/api/flow/tape")
def get_tape(symbol: str, limit: int = Query(default=200, ge=1, le=2000), min_notional: Optional[float] = None, market: Literal["spot", "futures"] = "spot"):
    check_flow_enabled()
    selected = _market_hub(market)
    sym = _normalize_symbol(symbol)
    state = selected.get_state(sym)
    if not state:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False, "market": market}
        
    tape_list = list(state["buffers"].tape)
    if min_notional:
        tape_list = [t for t in tape_list if t.quote_qty >= min_notional]
        
    return {"symbol": sym, "market": market, "entries": tape_list[-limit:]}

@router.get("/api/flow/heatmap")
def get_heatmap(symbol: str, window_sec: Optional[int] = Query(default=None, ge=1, le=600), tick_group: Optional[float] = Query(default=None, gt=0, allow_inf_nan=False), market: Literal["spot", "futures"] = "spot"):
    check_flow_enabled()
    selected = _market_hub(market)
    sym = _normalize_symbol(symbol)
    state = selected.get_state(sym)
    if not state:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False, "market": market}

    cache_key = f"flow_{market}_{selected.cache_generation}_heatmap_{sym}_{window_sec}_{tick_group}"
    cached = _get_cached(cache_key, ttl=1.0)
    if cached: return cached

    snapshot = selected.get_heatmap_snapshot(sym)
    if snapshot is None:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False, "market": market}

    res = snapshot.model_dump()
    res["market"] = market
    res["server_ts"] = int(time.time() * 1000)
    _set_cached(cache_key, res)
    return res

@router.get("/api/flow/volume-profile")
def get_volume_profile(symbol: str, mode: str = "SESSION", start_ts: Optional[int] = None, end_ts: Optional[int] = None, tick_group: Optional[float] = Query(default=None, gt=0, allow_inf_nan=False), market: Literal["spot", "futures"] = "spot"):
    check_flow_enabled()
    selected = _market_hub(market)
    if mode not in ("SESSION", "VISIBLE", "FIXED_RANGE"):
        raise HTTPException(status_code=422, detail=f"Invalid mode '{mode}'. Allowed: SESSION, VISIBLE, FIXED_RANGE")
    sym = _normalize_symbol(symbol)
    if not selected.get_state(sym):
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False, "market": market}

    cache_key = f"flow_{market}_{selected.cache_generation}_profile_{sym}_{mode}_{start_ts}_{end_ts}_{tick_group}"
    cached = _get_cached(cache_key, ttl=2.0)
    if cached: return cached

    snapshot = selected.get_volume_profile(sym, mode=mode, start_ts=start_ts, end_ts=end_ts, tick_group=tick_group)
    if snapshot is None:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False, "market": market}

    res = snapshot.model_dump()
    res["market"] = market
    res["server_ts"] = int(time.time() * 1000)
    _set_cached(cache_key, res)
    return res

@router.get("/api/flow/cvd")
def get_cvd(symbol: str, interval: str = "1m", limit: int = Query(default=240, ge=1, le=240), market: Literal["spot", "futures"] = "spot"):
    check_flow_enabled()
    selected = _market_hub(market)
    sym = _normalize_symbol(symbol)
    state = selected.get_state(sym)
    if not state:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False, "market": market}

    cache_key = f"flow_{market}_{selected.cache_generation}_cvd_{sym}_{interval}_{limit}"
    cached = _get_cached(cache_key, ttl=1.0)
    if cached: return cached

    points = selected.get_cvd(sym, limit=limit)
    metrics = selected.get_metrics(sym)
    res = {
        "symbol": sym, "market": market,
        "interval": interval,
        "points": points,
        "vwap": metrics.vwap if metrics else 0.0,
        "vwap_upper_1": metrics.vwap_upper_1 if metrics else 0.0,
        "vwap_lower_1": metrics.vwap_lower_1 if metrics else 0.0,
        "server_ts": int(time.time() * 1000)
    }
    _set_cached(cache_key, res)
    return res

@router.get("/api/flow/metrics")
def get_metrics(symbol: str, market: Literal["spot", "futures"] = "spot"):
    check_flow_enabled()
    selected = _market_hub(market)
    sym = _normalize_symbol(symbol)
    if not selected.get_state(sym):
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False, "market": market}

    cache_key = f"flow_{market}_{selected.cache_generation}_metrics_{sym}"
    cached = _get_cached(cache_key, ttl=1.0)
    if cached: return cached

    metrics = selected.get_metrics(sym)
    if metrics is None:
        return {"success": False, "error": "No metrics available yet", "subscribed": True, "market": market}

    res = metrics.model_dump()
    res["success"] = True
    res["market"] = market
    res["server_ts"] = int(time.time() * 1000)
    _set_cached(cache_key, res)
    return res

@router.post("/api/flow/subscribe")
async def subscribe_symbol(req: SubscribeRequest):
    market = req.market
    check_flow_enabled()
    selected = _market_hub(market)
    sym = _normalize_symbol(req.symbol)
    try:
        await selected.subscribe(sym)
    except ValueError as exc:
        raise HTTPException(status_code=429 if "limit" in str(exc) else 422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Market stream unavailable") from exc
    return {"success": True, "symbol": sym, "market": market, "status": "Subscribed"}

@router.post("/api/flow/unsubscribe")
async def unsubscribe_symbol(req: UnsubscribeRequest):
    market = req.market
    check_flow_enabled()
    selected = _market_hub(market)
    sym = _normalize_symbol(req.symbol)
    await selected.unsubscribe(sym)
    return {"success": True, "symbol": sym, "market": market}

@router.get("/api/flow/symbol-info")
def get_symbol_info(symbol: str, market: Literal["spot", "futures"] = "spot"):
    check_flow_enabled()
    selected = _market_hub(market)
    sym = _normalize_symbol(symbol)
    state = selected.get_state(sym)
    if not state:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False, "market": market}

    cache_key = f"flow_{market}_{selected.cache_generation}_symbol_info_{sym}"
    cached = _get_cached(cache_key, ttl=86400.0)
    if cached: return cached

    tick_size = state["book"].tick_size
    filters = getattr(selected.connector, "symbol_filters", {}).get(sym, {})
    res = {
        "success": True,
        "symbol": sym, "market": market,
        "tick_size": tick_size,
        "step_size": float(filters.get("step_size", 0.0) or 0.0),
        "min_notional": float(filters.get("min_notional", 0.0) or 0.0),
        "price_precision": int(filters.get("price_precision", 0) or 0),
        "qty_precision": int(filters.get("qty_precision", 0) or 0),
        "default_tick_group": settings.flow_tick_group_base(sym, tick_size),
        "server_ts": int(time.time() * 1000)
    }
    _set_cached(cache_key, res)
    return res
