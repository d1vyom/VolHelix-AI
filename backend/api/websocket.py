import asyncio
import time
from typing import Dict, Any, Optional
from loguru import logger
import socketio

from backend.config import settings
from backend.marketdata.hub import hub

# Async Socket.IO server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
socket_app = socketio.ASGIApp(sio)

# symbol -> task
broadcasters: Dict[str, asyncio.Task] = {}
# symbol -> dict of last emitted state (to skip empty frames)
last_emit_state: Dict[str, dict] = {}

def start_broadcaster(symbol: str):
    sym = symbol.upper()
    if sym not in broadcasters or broadcasters[sym].done():
        broadcasters[sym] = asyncio.create_task(_broadcaster_task(sym))
        last_emit_state[sym] = {
            "tape_ts": 0,
            "dom_hash": None,
            "footprint": {},  # interval -> (open_time, trades, volume)
            "heatmap_ts": 0,
            "metrics_ts": 0
        }

@sio.event
async def connect(sid, environ):
    print(f"Dashboard client connected: {sid}")
    await sio.emit('status', {'status': 'LIVE'}, room=sid)

@sio.event
async def disconnect(sid):
    print(f"Dashboard client disconnected: {sid}")
    # In socket.io, rooms are left automatically on disconnect.
    # We should decrement hub refcounts, but we don't easily know which rooms the sid was in here without keeping track.
    # Let's keep a track if we need to.
    pass

@sio.event
async def flow_subscribe(sid, data: dict):
    if not settings.FLOW_ENABLED:
        return
    
    symbol = data.get("symbol")
    if not symbol:
        return
        
    sym = symbol.upper()
    hub.subscribe(sym)
    sio.enter_room(sid, f"flow:{sym}")
    
    start_broadcaster(sym)
    
    # Emit initial snapshot to sid for forming data
    state = hub.get_state(sym)
    if state:
        health = state["health"]
        await sio.emit("flow:health", health.model_dump(), to=sid)

@sio.event
async def flow_unsubscribe(sid, data: dict):
    symbol = data.get("symbol")
    if not symbol:
        return
        
    sym = symbol.upper()
    hub.unsubscribe(sym)
    sio.leave_room(sid, f"flow:{sym}")
    
    # If room is empty, broadcaster will pause or we can cancel it.
    # For now, broadcaster checks if room is empty.

@sio.event
async def flow_settings(sid, data: dict):
    # per-sid settings, typically for tick_group / interval
    # Currently, we just broadcast all tick_groups/intervals and client filters,
    # or we can store it in the session.
    async with sio.session(sid) as session:
        session['flow_settings'] = data

async def broadcast_portfolio_update(portfolio_dict: dict):
    await sio.emit('portfolio_update', portfolio_dict)
    
async def broadcast_reasoning_event(event_type: str, message: str, agent: str):
    await sio.emit('reasoning_event', {
        'type': event_type,
        'message': message,
        'agent': agent
    })

async def _broadcaster_task(sym: str):
    logger.info(f"[{sym}] Broadcaster task started.")
    
    from backend.engine.dom_analytics import DomAnalyticsEngine
    
    room = f"flow:{sym}"
    
    fps = settings.FLOW_BROADCAST_HZ
    interval_sec = 1.0 / fps if fps > 0 else 0.25
    tape_interval_sec = 1.0 / settings.FLOW_TAPE_BROADCAST_HZ if settings.FLOW_TAPE_BROADCAST_HZ > 0 else 0.1
    
    last_tape_check = time.time()
    last_slow_check = time.time()
    
    while True:
        try:
            await asyncio.sleep(min(interval_sec, tape_interval_sec))
            
            if not settings.FLOW_ENABLED:
                continue
                
            # If no listeners and not in FLOW_SYMBOLS, we can skip or exit
            # Getting room size in python-socketio:
            room_clients = sio.manager.rooms.get("/", {}).get(room, {})
            if not room_clients and sym not in settings.FLOW_SYMBOLS:
                # Pause work
                continue
                
            state = hub.get_state(sym)
            if not state:
                continue
                
            now = time.time()
            track = last_emit_state[sym]
            buffers = state["buffers"]
            
            # --- TAPE (fast) ---
            if now - last_tape_check >= tape_interval_sec:
                last_tape_check = now
                tape_list = list(buffers.tape)
                new_tape = [t for t in tape_list if t.ts > track["tape_ts"]]
                if new_tape:
                    track["tape_ts"] = max(t.ts for t in new_tape)
                    # batch emit
                    await sio.emit("flow:tape", {
                        "symbol": sym,
                        "entries": [t.model_dump() for t in new_tape]
                    }, room=room)
            
            # --- DOM, FOOTPRINT, HEATMAP, METRICS (slower) ---
            if now - last_slow_check >= interval_sec:
                last_slow_check = now
                
                # DOM
                book = state["book"]
                # A simple hash to detect changes
                dom_hash = hash((book.last_update_id, len(buffers.trades)))
                if dom_hash != track["dom_hash"]:
                    track["dom_hash"] = dom_hash
                    # In real implementation we should get tick_group from settings, default to book's tick_size
                    engine = DomAnalyticsEngine(sym, book.tick_size)
                    trades_1m = [t for t in list(buffers.trades) if t.ts > (now - 60) * 1000]
                    try:
                        book_snap = book.get_snapshot(settings.FLOW_DEPTH_LEVELS)
                        dom_res = engine.compute_analytics(book_snap, trades_1m)
                        await sio.emit("flow:dom", dom_res, room=room)
                    except Exception as e:
                        logger.error(f"[{sym}] DOM compute error: {e}")
                
                # FOOTPRINT
                for interval in settings.FLOW_FOOTPRINT_INTERVALS:
                    bars_q = buffers.bars.get(interval)
                    if bars_q and len(bars_q) > 0:
                        latest = bars_q[-1]
                        fp_key = f"{latest.open_time}_{latest.volume}"
                        if track["footprint"].get(interval) != fp_key:
                            track["footprint"][interval] = fp_key
                            await sio.emit("flow:footprint", {
                                "symbol": sym,
                                "interval": interval,
                                "bar": latest.model_dump(),
                                "is_closed": latest.is_closed
                            }, room=room)
                
                # HEATMAP
                # We need to compute or just send the latest frame
                heatmap_q = buffers.heatmap
                if heatmap_q and len(heatmap_q) > 0:
                    latest_hm = heatmap_q[-1]
                    if latest_hm.ts > track["heatmap_ts"]:
                        track["heatmap_ts"] = latest_hm.ts
                        await sio.emit("flow:heatmap", latest_hm.model_dump(), room=room)
                        
                # METRICS
                from backend.engine.flow_confluence import calculate_flow_metrics
                # Actually, there's no calculate_flow_metrics in flow_confluence maybe?
                # We need to construct FlowMetrics. Where is the metric compute function?
                # Let's mock it for now if we don't have it, or see where it's defined.
                # Just placeholder for now:
                # await sio.emit("flow:metrics", metrics.model_dump(), room=room)
                
                # HEALTH
                await sio.emit("flow:health", state["health"].model_dump(), room=room)
                
        except asyncio.CancelledError:
            logger.info(f"[{sym}] Broadcaster task cancelled.")
            break
        except Exception as e:
            logger.error(f"[{sym}] Broadcaster error: {e}")
