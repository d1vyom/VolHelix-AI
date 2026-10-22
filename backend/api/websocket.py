"""Fixed-rate, market-scoped Socket.IO orderflow transport."""
import asyncio
import time
from typing import Any
from loguru import logger
import socketio

from backend.config import settings
from backend.marketdata.hub import hub, get_hub
from backend.api.flow_schemas import SubscribeRequest

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=settings.CORS_ORIGINS)
socket_app = socketio.ASGIApp(sio)
broadcasters: dict[str, asyncio.Task] = {}
last_emit_state: dict[str, dict] = {}
_sid_subscriptions: dict[str, set[tuple[str, str]]] = {}
_sid_locks: dict[str, asyncio.Lock] = {}
_room_refs: dict[str, int] = {}


def _selected_hub(market: str):
    return hub if market == "spot" else get_hub(market)


def _room(market: str, symbol: str) -> str:
    return f"flow:{market}:{symbol}"


def start_broadcaster(symbol: str, market: str = "spot") -> None:
    """Create one shared fixed-rate broadcaster per market/symbol room."""
    room = _room(market, symbol)
    if room not in broadcasters or broadcasters[room].done():
        last_emit_state[room] = {"tape_last": None, "dom_hash": None,
                                 "footprint": {}, "heatmap_ts": 0, "metrics_ts": 0}
        broadcasters[room] = asyncio.create_task(_broadcaster_task(symbol, market))


async def _release(sid: str, market: str, symbol: str) -> None:
    key = (market, symbol)
    owned = _sid_subscriptions.get(sid, set())
    if key not in owned:
        return
    owned.remove(key)
    room = _room(market, symbol)
    _room_refs[room] -= 1
    if _room_refs[room] <= 0:
        _room_refs.pop(room, None)
        task = broadcasters.pop(room, None)
        # Detach this generation before yielding; a new SID can replace it below.
        last_emit_state.pop(room, None)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    await _selected_hub(market).unsubscribe(symbol)
    await sio.leave_room(sid, room)


@sio.event
async def connect(sid, environ):
    """A browser socket handshake is not evidence of live market data."""
    await sio.emit("status", {"status": "WAITING"}, room=sid)


@sio.event
async def disconnect(sid, reason=None):
    """Release every owned market subscription exactly once."""
    async with _sid_locks.setdefault(sid, asyncio.Lock()):
        for market, symbol in list(_sid_subscriptions.get(sid, set())):
            await _release(sid, market, symbol)
        _sid_subscriptions.pop(sid, None)
    _sid_locks.pop(sid, None)


@sio.event
async def flow_subscribe(sid, data: dict):
    """Validate market selection and await ingestion before acknowledging demand."""
    try:
        req = SubscribeRequest.model_validate(data)
        market, symbol = req.market, req.symbol.upper()
        room = _room(market, symbol)
        async with _sid_locks.setdefault(sid, asyncio.Lock()):
            owned = _sid_subscriptions.setdefault(sid, set())
            if (market, symbol) not in owned:
                selected = _selected_hub(market)
                await selected.subscribe(symbol)
                try:
                    await sio.enter_room(sid, room)
                except BaseException:
                    await selected.unsubscribe(symbol)
                    raise
                owned.add((market, symbol))
                _room_refs[room] = _room_refs.get(room, 0) + 1
                start_broadcaster(symbol, market)
            health = _selected_hub(market).get_state(symbol)["health"].model_dump()
            await sio.emit("flow:health", health, to=sid)
            return {"success": True, "market": market, "symbol": symbol,
                    "room": room, "status": health["status"]}
    except Exception as exc:
        error = {"success": False, "error": str(exc)}
        await sio.emit("flow:error", error, to=sid)
        return error


@sio.event
async def flow_unsubscribe(sid, data: dict):
    """Release only subscriptions owned by this browser socket."""
    try:
        req = SubscribeRequest.model_validate(data)
    except ValueError:
        return {"success": False, "error": "Invalid flow selection"}
    async with _sid_locks.setdefault(sid, asyncio.Lock()):
        await _release(sid, req.market, req.symbol.upper())
    return {"success": True, "market": req.market, "symbol": req.symbol.upper()}


@sio.event
async def flow_settings(sid, data: dict):
    async with sio.session(sid) as session:
        session["flow_settings"] = data


async def stop_broadcasters() -> None:
    """Await socket-owned demand cleanup and all fixed-rate tasks on shutdown."""
    for sid in list(_sid_subscriptions):
        await disconnect(sid)
    tasks = list(broadcasters.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    broadcasters.clear()
    last_emit_state.clear()
    _room_refs.clear()
    _sid_locks.clear()


async def broadcast_portfolio_update(portfolio_dict: dict):
    await sio.emit("portfolio_update", portfolio_dict)


async def broadcast_reasoning_event(event_type: str, message: str, agent: str):
    await sio.emit("reasoning_event", {"type": event_type, "message": message, "agent": agent})


async def _broadcaster_task(sym: str, market: str = "spot") -> None:
    room = _room(market, sym)
    selected = _selected_hub(market)
    slow_interval = 1 / max(settings.FLOW_BROADCAST_HZ, 1)
    tape_interval = 1 / max(settings.FLOW_TAPE_BROADCAST_HZ, 1)
    last_tape_check = last_slow_check = time.monotonic()

    async def emit(event: str, payload: Any) -> None:
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump()
        await sio.emit(event, {**payload, "symbol": sym, "market": market}, room=room)

    while True:
        try:
            await asyncio.sleep(min(slow_interval, tape_interval))
            if not settings.FLOW_ENABLED:
                continue
            state = selected.get_state(sym)
            if not state:
                continue
            now = time.monotonic()
            track = last_emit_state[room]
            buffers = state["buffers"]
            if now - last_tape_check >= tape_interval:
                last_tape_check = now
                new_tape = []
                for entry in reversed(buffers.tape):
                    if entry is track["tape_last"] or len(new_tape) >= 200:
                        break
                    new_tape.append(entry)
                if new_tape:
                    track["tape_last"] = new_tape[0]
                    await emit("flow:tape", {"entries": [t.model_dump() for t in reversed(new_tape)]})
            if now - last_slow_check < slow_interval:
                continue
            last_slow_check = now
            book = state["book"]
            dom_key = (book.last_update_id, len(buffers.trades), state["health"].last_trade_ts)
            if dom_key != track["dom_hash"]:
                track["dom_hash"] = dom_key
                dom = selected.get_dom(sym, settings.FLOW_DEPTH_LEVELS)
                if dom is not None:
                    await emit("flow:dom", dom)
            for interval in settings.FLOW_FOOTPRINT_INTERVALS:
                bars = selected.get_footprint_bars(sym, interval, limit=1)
                if bars:
                    latest = bars[-1]
                    key = (latest.open_time, latest.volume, latest.is_closed)
                    if track["footprint"].get(interval) != key:
                        track["footprint"][interval] = key
                        await emit("flow:footprint", {"interval": interval, "bar": latest.model_dump(),
                                                      "is_closed": latest.is_closed})
            engine = selected.heatmap_engines.get(sym)
            if engine and engine.frames:
                frame = engine.frames[-1]
                if frame.ts_bin > track["heatmap_ts"]:
                    track["heatmap_ts"] = frame.ts_bin
                    await emit("flow:heatmap", frame)
            metrics = selected.get_metrics(sym)
            if metrics is not None and metrics.ts > track["metrics_ts"]:
                track["metrics_ts"] = metrics.ts
                await emit("flow:metrics", metrics)
            await emit("flow:health", state["health"])
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception(f"[{market}:{sym}] Broadcaster error")
