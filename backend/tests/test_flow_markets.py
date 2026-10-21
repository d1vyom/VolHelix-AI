"""Network-free market stream, synchronization, and demand lifecycle contracts."""
import asyncio
import importlib
import time
from unittest.mock import AsyncMock

import pytest

from backend.config import settings
from backend.marketdata.hub import MarketDataHub
from backend.marketdata.models import BookDelta, BookSnapshot
from backend.marketdata.orderbook import LocalOrderBook


@pytest.fixture
def anyio_backend():
    return "asyncio"


def delta(first, final, previous=None):
    return BookDelta(symbol="BTCUSDT", first_update_id=first, final_update_id=final,
                     previous_final_update_id=previous, bids=[[100, 2]], asks=[], event_ts=1000)


def snapshot(last=10):
    return BookSnapshot(symbol="BTCUSDT", last_update_id=last, bids=[[99, 1]],
                        asks=[[101, 1]], ts=1000, source="REST")


def trade(price="100", symbol="BTCUSDT", ts=None):
    return {"e": "aggTrade", "s": symbol, "a": 1, "p": price, "q": "2",
            "m": False, "T": ts or int(time.time() * 1000)}


def test_futures_book_bridges_snapshot_inclusively_and_checks_pu():
    book = LocalOrderBook("BTCUSDT", .01, market="futures")
    book.process_diff(delta(8, 9, 7))
    book.process_diff(delta(9, 10, 8))  # u == snapshot is retained for Futures.
    assert book.process_snapshot(snapshot())
    assert book.last_update_id == 10
    assert book.process_diff(delta(12, 14, 10))  # U need not equal previous u+1.
    assert not book.process_diff(delta(15, 16, 13))
    assert not book.is_synced
    assert book.process_snapshot(snapshot(15))  # offending event retained for recovery
    assert book.last_update_id == 16


def test_spot_ignores_stale_events_but_preserves_first_sequence_rule():
    book = LocalOrderBook("BTCUSDT", .01)
    book.process_diff(delta(9, 10))
    assert not book.process_snapshot(snapshot())
    book.process_diff(delta(10, 12))
    assert book.process_snapshot(snapshot())
    assert book.process_diff(delta(10, 12))
    assert book.last_update_id == 12
    assert not book.process_diff(delta(14, 15))


def test_futures_connector_routes_and_parses_independent_stream_groups():
    from backend.marketdata.connectors.binance_futures import BinanceFuturesConnector
    connector = BinanceFuturesConnector()
    assert connector.stream_groups("BTCUSDT") == {
        "wss://fstream.binance.com/public": ["btcusdt@depth@100ms"],
        "wss://fstream.binance.com/market": ["btcusdt@aggTrade"],
    }
    assert connector.parse(trade()).side == "BUY"
    event = connector.parse({"e": "depthUpdate", "s": "BTCUSDT", "U": 12,
                             "u": 14, "pu": 10, "b": [["100", "2"]], "a": [], "E": 1000})
    assert event.previous_final_update_id == 10


@pytest.fixture
def hubs(monkeypatch):
    module = importlib.import_module("backend.marketdata.hub")
    spot, futures = MarketDataHub("spot"), MarketDataHub("futures")
    monkeypatch.setattr(module, "_hubs", {"spot": spot, "futures": futures})
    monkeypatch.setattr(settings, "FLOW_ENABLED", True)
    monkeypatch.setattr(settings, "FLOW_SYMBOLS_STR", "BTCUSDT")
    for hub in (spot, futures):
        hub.connector.tick_size = AsyncMock(return_value=.01)
        hub.connector.depth_snapshot = AsyncMock(return_value=snapshot())
        hub.stream_manager.start = AsyncMock()
        hub.stream_manager.update_streams = AsyncMock()
        hub.stream_manager.stop = AsyncMock()
        hub.flow_store.start = AsyncMock()
        hub.flow_store.stop = AsyncMock()
    return spot, futures


@pytest.mark.anyio
async def test_flow_state_is_market_scoped_and_new_symbol_ingests(hubs):
    spot, futures = hubs
    try:
        await spot.start()
        assert list(spot.books) == ["BTCUSDT"]
        assert not futures.books
        await futures.subscribe("ETHUSDT")
        assert set(futures.books) == {"ETHUSDT"}
        futures.stream_manager.update_streams.assert_awaited()
        assert "ethusdt@aggTrade" in str(futures.stream_manager.update_streams.call_args)
        await spot.subscribe("ETHUSDT")
        spot._on_message(trade("100", "ETHUSDT"))
        futures._on_message(trade("200", "ETHUSDT"))
        assert spot.get_metrics("ETHUSDT").price == 100
        assert futures.get_metrics("ETHUSDT").price == 200
        assert spot.get_state("ETHUSDT")["health"].market == "spot"
        assert futures.get_state("ETHUSDT")["health"].market == "futures"
        assert futures.health()["ETHUSDT"].status == "WAITING"  # trade alone is not LIVE
    finally:
        await spot.stop()
        await futures.stop()


@pytest.mark.anyio
async def test_subscription_limit_rejects_excess_and_releases_idle_symbols(hubs, monkeypatch):
    spot, futures = hubs
    monkeypatch.setattr(settings, "FLOW_MAX_ACTIVE_SYMBOLS", 2)
    try:
        await spot.start()
        await spot.subscribe("BTCUSDT")  # pinned does not consume demand cap
        await spot.subscribe("ETHUSDT")
        await futures.subscribe("ETHUSDT")
        with pytest.raises(ValueError, match="limit"):
            await futures.subscribe("SOLUSDT")
        assert "SOLUSDT" not in futures.books
        await spot.unsubscribe("ETHUSDT")
        assert "ETHUSDT" not in spot.books
        await futures.subscribe("SOLUSDT")
        await spot.unsubscribe("BTCUSDT")
        assert "BTCUSDT" in spot.books
    finally:
        await spot.stop()
        await futures.stop()


@pytest.mark.anyio
async def test_concurrent_subscriptions_initialize_once_and_shutdown_cancels_tasks(hubs):
    spot, futures = hubs
    try:
        await asyncio.gather(*(futures.subscribe("ETHUSDT") for _ in range(4)))
        assert futures.dynamic_subs == {"ETHUSDT": 4}
        futures.connector.tick_size.assert_awaited_once()
        await asyncio.gather(*(futures.unsubscribe("ETHUSDT") for _ in range(4)))
        assert not futures.books
        assert not futures.dynamic_subs
    finally:
        await spot.stop()
        await futures.stop()
    assert not futures.stream_manager.active_chunks
    assert not futures._resync_tasks
    assert futures._msg_rate_task is None or futures._msg_rate_task.done()


@pytest.mark.anyio
async def test_last_unsubscribe_stops_broadcaster_and_disconnect_is_idempotent(hubs, monkeypatch):
    ws = importlib.import_module("backend.api.websocket")
    spot, futures = hubs
    monkeypatch.setattr(ws, "hub", spot)
    monkeypatch.setattr(ws.sio, "enter_room", AsyncMock())
    monkeypatch.setattr(ws.sio, "leave_room", AsyncMock())
    monkeypatch.setattr(ws.sio, "emit", AsyncMock())
    data = {"symbol": "ETHUSDT", "market": "futures"}
    try:
        await asyncio.gather(ws.flow_subscribe("one", data), ws.flow_subscribe("one", data))
        assert futures.dynamic_subs == {"ETHUSDT": 1}
        await ws.flow_subscribe("two", data)
        assert futures.dynamic_subs == {"ETHUSDT": 2}
        ws.sio.enter_room.assert_any_await("one", "flow:futures:ETHUSDT")
        task = ws.broadcasters["flow:futures:ETHUSDT"]
        await ws.disconnect("one")
        assert futures.dynamic_subs == {"ETHUSDT": 1}
        assert not task.done()
        await ws.flow_unsubscribe("two", data)
        await ws.disconnect("two")
        assert not futures.dynamic_subs
        assert "flow:futures:ETHUSDT" not in ws.broadcasters
        assert "flow:futures:ETHUSDT" not in ws.last_emit_state
        assert task.done()
    finally:
        await ws.stop_broadcasters()
        await spot.stop()
        await futures.stop()


@pytest.mark.anyio
async def test_snapshot_error_is_contained_and_resync_is_deduplicated(hubs):
    spot, futures = hubs
    try:
        await futures.subscribe("ETHUSDT")
        futures.connector.depth_snapshot = AsyncMock(side_effect=RuntimeError("offline"))
        for _ in range(10):
            futures._trigger_resync("ETHUSDT")
        assert len(futures._resync_tasks) == 1
        await asyncio.gather(*futures._resync_tasks)
        assert not futures.books["ETHUSDT"].is_syncing
        assert futures.health()["ETHUSDT"].status != "LIVE"
    finally:
        await spot.stop()
        await futures.stop()


@pytest.mark.anyio
async def test_rest_market_cache_hydration_and_validation(hubs, monkeypatch):
    import httpx
    routes = importlib.import_module("backend.api.flow_routes")
    from backend.main import fastapi_app
    spot, futures = hubs
    monkeypatch.setattr(routes, "hub", spot)
    try:
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for market, price in (("spot", "100"), ("futures", "200")):
                response = await client.post("/api/flow/subscribe", json={"market": market, "symbol": "ETHUSDT"})
                assert response.status_code == 200
                assert response.json()["market"] == market
                (spot if market == "spot" else futures)._on_message(trade(price, "ETHUSDT"))
            for market, price in (("spot", 100), ("futures", 200), ("spot", 100)):
                response = await client.get("/api/flow/metrics", params={"market": market, "symbol": "ETHUSDT"})
                assert response.json()["market"] == market
                assert response.json()["price"] == price
            response = await client.get("/api/flow/metrics?symbol=ETHUSDT")
            assert response.json()["market"] == "spot"
            assert response.json()["price"] == 100
            assert (await client.get("/api/flow/status?market=futures")).json()["symbols"] == ["ETHUSDT"]
            await client.post("/api/flow/unsubscribe", json={"market": "futures", "symbol": "ETHUSDT"})
            await client.post("/api/flow/subscribe", json={"market": "futures", "symbol": "ETHUSDT"})
            futures._on_message(trade("300", "ETHUSDT"))
            refreshed = await client.get("/api/flow/metrics?market=futures&symbol=ETHUSDT")
            assert refreshed.json()["price"] == 300  # never hydrate prior subscription generation
            for path in ("status?market=invalid", "dom?symbol=ETHUSDT&levels=1000000",
                         "footprint?symbol=ETHUSDT&limit=-1", "tape?symbol=ETHUSDT&limit=1000000",
                         "volume-profile?symbol=ETHUSDT&tick_group=nan"):
                assert (await client.get(f"/api/flow/{path}")).status_code == 422
            assert (await client.post("/api/flow/subscribe", json={"market": "invalid", "symbol": "ETHUSDT"})).status_code == 422
            futures.connector.tick_size.side_effect = ValueError("not listed")
            response = await client.post("/api/flow/subscribe", json={"market": "futures", "symbol": "UNKNOWN"})
            assert response.status_code == 422
            assert "UNKNOWN" not in futures.dynamic_subs
            assert "UNKNOWN" not in futures.books
    finally:
        await spot.stop()
        await futures.stop()


@pytest.mark.anyio
async def test_real_stream_manager_opens_separate_routes_and_awaits_shutdown(monkeypatch):
    from backend.marketdata.stream_manager import StreamManager
    from backend.marketdata.connectors.binance_futures import BinanceFuturesConnector
    streams = importlib.import_module("backend.marketdata.stream_manager")
    received, resyncs, sockets = [], [], {}
    got_both = asyncio.Event()

    class PublicSocket:
        def __init__(self, url):
            self.url = url
            self.queue = asyncio.Queue()
            self.closed = False
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            self.closed = True
        def __aiter__(self):
            return self
        async def __anext__(self):
            import json
            return json.dumps(await self.queue.get())
        async def close(self):
            self.closed = True

    def connect(url, **kwargs):
        socket = PublicSocket(url)
        sockets[url] = socket
        event = (trade() if "/market/" in url else
                 {"e": "depthUpdate", "s": "BTCUSDT", "U": 10, "u": 12, "pu": 9, "b": [], "a": []})
        socket.queue.put_nowait(event)
        return socket

    def receive(data):
        received.append(data)
        if len(received) == 2:
            got_both.set()

    monkeypatch.setattr(streams.websockets, "connect", connect)
    manager = StreamManager(receive, resyncs.append)
    try:
        await manager.start(BinanceFuturesConnector().stream_groups("BTCUSDT"))
        await asyncio.wait_for(got_both.wait(), 1)
        assert set(sockets) == {
            "wss://fstream.binance.com/public/stream?streams=btcusdt@depth@100ms",
            "wss://fstream.binance.com/market/stream?streams=btcusdt@aggTrade",
        }
        assert {event["e"] for event in received} == {"aggTrade", "depthUpdate"}
        assert resyncs == ["BTCUSDT"]  # trade reconnects must not reset the depth book
        tasks = [chunk.task for chunk in manager.active_chunks.values()]
    finally:
        await manager.stop()
    assert all(task.done() for task in tasks)
    assert all(socket.closed for socket in sockets.values())
    assert not manager.active_chunks


@pytest.mark.anyio
async def test_fixed_broadcasts_emit_real_market_tape_depth_heatmap_and_forming_cells(hubs, monkeypatch):
    ws = importlib.import_module("backend.api.websocket")
    spot, futures = hubs
    monkeypatch.setattr(ws, "hub", spot)
    monkeypatch.setattr(ws.sio, "enter_room", AsyncMock())
    monkeypatch.setattr(ws.sio, "leave_room", AsyncMock())
    monkeypatch.setattr(settings, "FLOW_BROADCAST_HZ", 20)
    monkeypatch.setattr(settings, "FLOW_TAPE_BROADCAST_HZ", 40)
    frames = []
    second_health = asyncio.Event()

    async def emit(event, payload, **kwargs):
        frames.append((event, payload, kwargs))
        if sum(frame[0] == "flow:health" for frame in frames) >= 3:
            second_health.set()

    monkeypatch.setattr(ws.sio, "emit", emit)
    try:
        await ws.flow_subscribe("viewer", {"market": "futures", "symbol": "ETHUSDT"})
        futures._on_message(trade("200", "ETHUSDT"))
        now = int(time.time() * 1000)
        futures._on_message({"e": "depthUpdate", "s": "ETHUSDT", "U": 10, "u": 12,
                             "pu": 9, "b": [["199", "3"]], "a": [["201", "4"]], "E": now})
        await asyncio.gather(*futures._resync_tasks)
        book = futures.books["ETHUSDT"]
        assert book.is_synced
        futures._sample_heatmap("ETHUSDT", now)
        await asyncio.wait_for(second_health.wait(), 1)
        by_event = {event: payload for event, payload, kwargs in frames if "room" in kwargs}
        assert set(by_event) >= {"flow:tape", "flow:dom", "flow:footprint", "flow:heatmap", "flow:metrics", "flow:health"}
        for event, payload, kwargs in frames:
            assert payload["market"] == "futures"
            assert payload["symbol"] == "ETHUSDT"
            if "room" in kwargs:
                assert kwargs["room"] == "flow:futures:ETHUSDT"
        assert by_event["flow:tape"]["entries"][0]["price"] == 200
        assert by_event["flow:footprint"]["bar"]["cells"][0]["buy_volume"] == 2
        assert by_event["flow:health"]["status"] == "LIVE"
        # Two slow ticks, rather than a frame per incoming message.
        assert sum(event == "flow:metrics" for event, _, _ in frames) <= 3
    finally:
        await ws.stop_broadcasters()
        await spot.stop()
        await futures.stop()


@pytest.mark.anyio
async def test_health_requires_fresh_trade_and_book_and_reconnect_resyncs(hubs):
    spot, futures = hubs
    try:
        await futures.subscribe("ETHUSDT")
        futures._on_message(trade("200", "ETHUSDT"))
        assert futures.health()["ETHUSDT"].status == "WAITING"
        book = futures.books["ETHUSDT"]
        book.process_diff(delta(10, 12, 9))
        assert book.process_snapshot(snapshot())
        health = futures.health_state["ETHUSDT"]
        health.last_book_ts = int(time.time() * 1000)
        assert futures.health()["ETHUSDT"].status == "LIVE"
        health.last_trade_ts -= 20000
        assert futures.health()["ETHUSDT"].status == "STALE"
        futures.connector.depth_snapshot = AsyncMock(return_value=snapshot())
        futures._trigger_resync("ETHUSDT")
        assert not book.is_synced
        assert futures.health()["ETHUSDT"].status != "LIVE"
        await asyncio.gather(*futures._resync_tasks)
    finally:
        await spot.stop()
        await futures.stop()


@pytest.mark.anyio
async def test_unknown_high_price_symbol_has_bounded_footprint_rows_without_losing_volume(hubs):
    spot, futures = hubs
    try:
        await futures.subscribe("WIDEUSDT")
        futures._on_message(trade("50000", "WIDEUSDT"))
        futures._on_message({**trade("100000", "WIDEUSDT"), "a": 2})
        bar = futures.get_footprint_bars("WIDEUSDT")[0]
        assert (bar.high - bar.low) / bar.tick_group <= 512
        assert len(bar.cells) == 2
        assert sum(cell.buy_volume for cell in bar.cells) == bar.volume == 4
        assert bar.open == 50000 and bar.close == 100000
    finally:
        await spot.stop()
        await futures.stop()


@pytest.mark.anyio
async def test_failed_room_join_rolls_back_demand_and_shutdown_releases_both_markets(hubs, monkeypatch):
    ws = importlib.import_module("backend.api.websocket")
    spot, futures = hubs
    monkeypatch.setattr(ws, "hub", spot)
    monkeypatch.setattr(ws.sio, "emit", AsyncMock())
    monkeypatch.setattr(ws.sio, "leave_room", AsyncMock())
    monkeypatch.setattr(ws.sio, "enter_room", AsyncMock(side_effect=RuntimeError("gone")))
    try:
        result = await ws.flow_subscribe("gone", {"market": "futures", "symbol": "ETHUSDT"})
        assert not result["success"]
        assert not futures.dynamic_subs and not futures.books
        monkeypatch.setattr(ws.sio, "enter_room", AsyncMock())
        for market in ("spot", "futures"):
            await ws.flow_subscribe("viewer", {"market": market, "symbol": "ETHUSDT"})
        tasks = list(ws.broadcasters.values())
        await ws.stop_broadcasters()
        assert all(task.done() for task in tasks)
        assert not ws.broadcasters and not ws.last_emit_state and not ws._sid_subscriptions
        assert not spot.dynamic_subs and not futures.dynamic_subs
        assert "ETHUSDT" not in spot.books and "ETHUSDT" not in futures.books
    finally:
        await ws.stop_broadcasters()
        await spot.stop()
        await futures.stop()


@pytest.mark.anyio
async def test_startup_failure_is_retryable_and_disconnect_during_initialization_cleans_up(hubs, monkeypatch):
    ws = importlib.import_module("backend.api.websocket")
    spot, futures = hubs
    monkeypatch.setattr(ws, "hub", spot)
    monkeypatch.setattr(ws.sio, "emit", AsyncMock())
    monkeypatch.setattr(ws.sio, "enter_room", AsyncMock())
    monkeypatch.setattr(ws.sio, "leave_room", AsyncMock())
    futures.flow_store.start.side_effect = [RuntimeError("storage unavailable"), None]
    try:
        with pytest.raises(RuntimeError, match="storage unavailable"):
            await futures.subscribe("ETHUSDT")
        assert not futures._running
        assert not futures.dynamic_subs
        began, proceed = asyncio.Event(), asyncio.Event()
        async def tick_size(symbol):
            began.set()
            await proceed.wait()
            return .01
        futures.connector.tick_size = tick_size
        subscribing = asyncio.create_task(ws.flow_subscribe("leaving", {"market": "futures", "symbol": "ETHUSDT"}))
        await asyncio.wait_for(began.wait(), 1)
        disconnecting = asyncio.create_task(ws.disconnect("leaving"))
        proceed.set()
        await asyncio.gather(subscribing, disconnecting)
        assert "leaving" not in ws._sid_subscriptions
        assert not futures.dynamic_subs and not futures.books
        assert not ws.broadcasters
    finally:
        await ws.stop_broadcasters()
        await spot.stop()
        await futures.stop()
