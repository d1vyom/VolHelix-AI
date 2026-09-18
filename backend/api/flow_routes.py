from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
import time

from backend.config import settings
from backend.marketdata.hub import hub
from backend.api.flow_schemas import (
    StatusResponse, FootprintResponse, TapeResponse, CVDSnapshotResponse,
    SubscribeRequest, SubscribeResponse, UnsubscribeRequest, UnsubscribeResponse,
    SymbolInfoResponse
)
from backend.engine.flow_models import (
    DomAnalytics, HeatmapSnapshot, VolumeProfileSnapshot, FlowMetrics
)
from backend.api.routes import _normalize_symbol, _get_cached, _set_cached

router = APIRouter(tags=["order-flow"])

def check_flow_enabled():
    if not settings.FLOW_ENABLED:
        raise HTTPException(status_code=503, detail={"enabled": False, "reason": "Order flow engine is disabled via configuration"})

@router.get("/api/flow/status")
def get_flow_status():
    if not settings.FLOW_ENABLED:
        return StatusResponse(enabled=False, reason="Order flow disabled")
    return StatusResponse(
        enabled=True,
        symbols=list(hub.books.keys()),
        health=hub.health()
    )

@router.get("/api/flow/footprint")
def get_footprint(
    symbol: str, 
    interval: str = "1m", 
    limit: int = 60, 
    tick_group: Optional[float] = None
):
    check_flow_enabled()
    sym = _normalize_symbol(symbol)
    state = hub.get_state(sym)
    if not state:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False}
    
    cache_key = f"flow_footprint_{sym}_{interval}_{limit}_{tick_group}"
    cached = _get_cached(cache_key, ttl=1.0)
    if cached: return cached
    
    bars_deque = state["buffers"].bars.get(interval, [])
    bars_list = list(bars_deque)[-limit:]
    
    # tick_group is an override, but if it differs from what footprint.py uses we would need to re-aggregate.
    # For Phase 4 we can just return what we have in the buffers.
    actual_tick_group = bars_list[0].tick_group if bars_list else (tick_group or 10.0)

    res = {
        "symbol": sym,
        "interval": interval,
        "tick_group": actual_tick_group,
        "bars": [b.model_dump() for b in bars_list]
    }
    _set_cached(cache_key, res)
    return res

@router.get("/api/flow/dom")
def get_dom(symbol: str, levels: int = 20, tick_group: Optional[float] = None):
    check_flow_enabled()
    sym = _normalize_symbol(symbol)
    state = hub.get_state(sym)
    if not state:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False}
        
    cache_key = f"flow_dom_{sym}_{levels}_{tick_group}"
    cached = _get_cached(cache_key, ttl=0.25)
    if cached: return cached
    
    analytics = hub.get_dom(sym, levels)
    if analytics is None:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False}

    res = analytics.model_dump()
    res["server_ts"] = int(time.time() * 1000)
    _set_cached(cache_key, res)
    return res

@router.get("/api/flow/tape")
def get_tape(symbol: str, limit: int = 200, min_notional: Optional[float] = None):
    check_flow_enabled()
    sym = _normalize_symbol(symbol)
    state = hub.get_state(sym)
    if not state:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False}
        
    tape_list = list(state["buffers"].tape)
    if min_notional:
        tape_list = [t for t in tape_list if t.quote_qty >= min_notional]
        
    return {"symbol": sym, "entries": tape_list[-limit:]}

@router.get("/api/flow/heatmap")
def get_heatmap(symbol: str, window_sec: Optional[int] = None, tick_group: Optional[float] = None):
    check_flow_enabled()
    sym = _normalize_symbol(symbol)
    state = hub.get_state(sym)
    if not state:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False}

    cache_key = f"flow_heatmap_{sym}_{window_sec}_{tick_group}"
    cached = _get_cached(cache_key, ttl=1.0)
    if cached: return cached

    snapshot = hub.get_heatmap_snapshot(sym)
    if snapshot is None:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False}

    res = snapshot.model_dump()
    res["server_ts"] = int(time.time() * 1000)
    _set_cached(cache_key, res)
    return res

@router.get("/api/flow/volume-profile")
def get_volume_profile(symbol: str, mode: str = "SESSION", start_ts: Optional[int] = None, end_ts: Optional[int] = None, tick_group: Optional[float] = None):
    check_flow_enabled()
    if mode not in ("SESSION", "VISIBLE", "FIXED_RANGE"):
        raise HTTPException(status_code=422, detail=f"Invalid mode '{mode}'. Allowed: SESSION, VISIBLE, FIXED_RANGE")
    sym = _normalize_symbol(symbol)
    if not hub.get_state(sym):
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False}

    cache_key = f"flow_profile_{sym}_{mode}_{start_ts}_{end_ts}_{tick_group}"
    cached = _get_cached(cache_key, ttl=2.0)
    if cached: return cached

    snapshot = hub.get_volume_profile(sym, mode=mode, start_ts=start_ts, end_ts=end_ts, tick_group=tick_group)
    if snapshot is None:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False}

    res = snapshot.model_dump()
    res["server_ts"] = int(time.time() * 1000)
    _set_cached(cache_key, res)
    return res

@router.get("/api/flow/cvd")
def get_cvd(symbol: str, interval: str = "1m", limit: int = 240):
    check_flow_enabled()
    sym = _normalize_symbol(symbol)
    state = hub.get_state(sym)
    if not state:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False}

    cache_key = f"flow_cvd_{sym}_{interval}_{limit}"
    cached = _get_cached(cache_key, ttl=1.0)
    if cached: return cached

    points = hub.get_cvd(sym, limit=limit)
    metrics = hub.get_metrics(sym)
    res = {
        "symbol": sym,
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
def get_metrics(symbol: str):
    check_flow_enabled()
    sym = _normalize_symbol(symbol)
    if not hub.get_state(sym):
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False}

    cache_key = f"flow_metrics_{sym}"
    cached = _get_cached(cache_key, ttl=1.0)
    if cached: return cached

    metrics = hub.get_metrics(sym)
    if metrics is None:
        return {"success": False, "error": "No metrics available yet", "subscribed": True}

    res = metrics.model_dump()
    res["success"] = True
    res["server_ts"] = int(time.time() * 1000)
    _set_cached(cache_key, res)
    return res

@router.post("/api/flow/subscribe")
def subscribe_symbol(req: SubscribeRequest):
    check_flow_enabled()
    sym = _normalize_symbol(req.symbol)
    hub.subscribe(sym)
    return {"success": True, "symbol": sym, "status": "Subscribed"}

@router.post("/api/flow/unsubscribe")
def unsubscribe_symbol(req: UnsubscribeRequest):
    check_flow_enabled()
    sym = _normalize_symbol(req.symbol)
    hub.unsubscribe(sym)
    return {"success": True, "symbol": sym}

@router.get("/api/flow/symbol-info")
def get_symbol_info(symbol: str):
    check_flow_enabled()
    sym = _normalize_symbol(symbol)
    state = hub.get_state(sym)
    if not state:
        return {"success": False, "error": "Symbol not subscribed", "subscribed": False}

    cache_key = f"flow_symbol_info_{sym}"
    cached = _get_cached(cache_key, ttl=86400.0)
    if cached: return cached

    tick_size = state["book"].tick_size
    filters = getattr(hub.connector, "symbol_filters", {}).get(sym, {})
    res = {
        "success": True,
        "symbol": sym,
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
