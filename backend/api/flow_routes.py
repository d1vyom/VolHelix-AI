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
    
    # we need dom_analytics to compute from book
    # we'll implement the call to dom_analytics engine here
    from backend.engine.dom_analytics import DomAnalyticsEngine
    engine = DomAnalyticsEngine(sym, tick_group or state["book"].tick_size)
    trades_1m = [t for t in state["buffers"].trades if t.ts > time.time() * 1000 - 60000]
    book_snap = state["book"].get_snapshot(levels) # dummy, we'll need a real snapshot
    
    res = engine.compute_analytics(book_snap, trades_1m)
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
        
    # We should get this from heatmap_engine
    return {"success": False, "error": "Not implemented completely yet", "subscribed": True}

@router.get("/api/flow/volume-profile")
def get_volume_profile(symbol: str, mode: str = "SESSION", start_ts: Optional[int] = None, end_ts: Optional[int] = None, tick_group: Optional[float] = None):
    check_flow_enabled()
    return {"success": False, "error": "Not implemented completely yet"}

@router.get("/api/flow/cvd")
def get_cvd(symbol: str, interval: str = "1m", limit: int = 240):
    check_flow_enabled()
    return {"success": False, "error": "Not implemented completely yet"}

@router.get("/api/flow/metrics")
def get_metrics(symbol: str):
    check_flow_enabled()
    return {"success": False, "error": "Not implemented completely yet"}

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
    # mock values
    return {
        "tick_size": 0.01,
        "step_size": 0.00001,
        "min_notional": 5.0,
        "price_precision": 2,
        "qty_precision": 5,
        "default_tick_group": 10.0
    }
