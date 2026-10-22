import asyncio
import math
import time
from typing import Dict, Callable, Any, Optional, Literal
from loguru import logger

from backend.config import settings
from backend.marketdata.models import StreamHealth
from backend.marketdata.buffers import SymbolBuffers
from backend.marketdata.orderbook import LocalOrderBook
from backend.engine.footprint import FootprintEngine
from backend.engine.delta_engine import DeltaEngine
from backend.engine.volume_profile import VolumeProfileEngine
from backend.engine.heatmap import HeatmapEngine
from backend.engine.dom_analytics import DomEngine
from backend.engine.tape_analytics import TapeEngine
from backend.engine.flow_models import FlowMetrics
from backend.marketdata.stream_manager import StreamManager
from backend.marketdata.connectors.binance_spot import BinanceSpotConnector
from backend.marketdata.connectors.binance_futures import BinanceFuturesConnector
from backend.store.flow_store import FlowStore
from pathlib import Path

class MarketDataHub:
    """Market-owned orderflow state; the module keeps one hub per market."""

    def __init__(self, market: str = "spot"):
        if market not in ("spot", "futures"):
            raise ValueError("market must be spot or futures")
        self.market = market
        self.connector = BinanceSpotConnector() if market == "spot" else BinanceFuturesConnector()
        self._subscription_lock = asyncio.Lock()
        self.cache_generation = 0
        self.pinned_symbols: set[str] = set()
        self._resync_by_symbol: dict[str, asyncio.Task] = {}
        self.stream_manager = StreamManager(callback=self._on_message, trigger_resync=self._trigger_resync)
        
        self.buffers: Dict[str, SymbolBuffers] = {}
        self.books: Dict[str, LocalOrderBook] = {}
        self.footprint_engines: Dict[str, Dict[str, FootprintEngine]] = {}
        self.delta_engines: Dict[str, DeltaEngine] = {}
        self.profile_engines: Dict[str, VolumeProfileEngine] = {}
        self.heatmap_engines: Dict[str, HeatmapEngine] = {}
        self.dom_engines: Dict[str, DomEngine] = {}
        self.tape_engines: Dict[str, TapeEngine] = {}
        self.health_state: Dict[str, StreamHealth] = {}
        
        self.listeners: list[Callable[[str, Any], None]] = []
        self.dynamic_subs: Dict[str, int] = {} # symbol -> refcount
        self.flow_store = FlowStore(str(Path(__file__).resolve().parents[1] / "data" / "flow.db"))
        
        self._resync_tasks: set[asyncio.Task] = set()
        self._persistence_task = None
        self._msg_rate_task = None
        self._msg_counters: Dict[str, int] = {}
        self._running = False
        
    async def start(self):
        """Starts the hub and websocket ingestion."""
        if not settings.FLOW_ENABLED or self._running:
            return
            
        self._running = True
        logger.info("MarketDataHub starting...")
        
        # Init state for static symbols
        self.pinned_symbols = set(settings.FLOW_SYMBOLS) if self.market == "spot" else set()
        for sym in self.pinned_symbols:
            try:
                await self._init_symbol_state(sym)
            except Exception as exc:
                logger.warning(f"[{self.market}:{sym}] Flow startup unavailable: {exc}")
            
        try:
            await self.flow_store.start()
            await self.stream_manager.start(self._stream_groups())
        except BaseException:
            self._running = False
            await self.stream_manager.stop()
            await self.flow_store.stop()
            raise

        self._msg_rate_task = asyncio.create_task(self._msg_rate_loop())

        if getattr(settings, "FLOW_PERSIST_BARS", False):
            self._persistence_task = asyncio.create_task(self._persist_bars_loop())

    async def _msg_rate_loop(self):
        """Derives an inbound messages/sec figure per symbol once a second."""
        while self._running:
            await asyncio.sleep(1)
            for sym, count in list(self._msg_counters.items()):
                health = self.health_state.get(sym)
                if health:
                    health.messages_per_sec = float(count)
                self._msg_counters[sym] = 0

    async def _persist_bars_loop(self):
        """Periodically scans buffers for closed bars and saves them."""
        # Simple polling approach since we don't have explicit event emitters on bar close
        last_saved: Dict[str, set] = {} # symbol_interval -> set(open_times)
        while self._running:
            await asyncio.sleep(10)
            active_keys = {f"{sym}_{interval}" for sym in self.buffers for interval in settings.FLOW_FOOTPRINT_INTERVALS}
            last_saved = {key: saved for key, saved in last_saved.items() if key in active_keys}
            for sym, buffers in list(self.buffers.items()):
                for interval, bars in buffers.bars.items():
                    key = f"{sym}_{interval}"
                    if key not in last_saved:
                        last_saved[key] = set()
                    
                    for b in list(bars):
                        if b.is_closed and b.open_time not in last_saved[key]:
                            await self.flow_store.save_bar(sym if self.market == "spot" else f"{self.market}:{sym}", interval, b.model_dump())
                            last_saved[key].add(b.open_time)
                    
                    # Cleanup old saved open_times to avoid memory leak
                    if len(last_saved[key]) > 1000:
                        keep = set(b.open_time for b in bars)
                        last_saved[key] = last_saved[key].intersection(keep)

    async def stop(self):
        """Stops ingestion and cleans up."""
        self._running = False
        await self.stream_manager.stop()
        tasks = list(self._resync_tasks)
        tasks.extend(t for t in (self._persistence_task, self._msg_rate_task) if t is not None)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self.flow_store.stop()
        self._resync_tasks.clear()
        self._resync_by_symbol.clear()
        self._persistence_task = self._msg_rate_task = None
        self.dynamic_subs.clear()
        for sym in list(self.books):
            self._drop_symbol(sym)

    async def _init_symbol_state(self, symbol: str):
        sym = self.connector.normalize_symbol(symbol)
        if sym not in self.books:
            tick_size = await self.connector.tick_size(sym)
            self.cache_generation += 1
            self.books[sym] = LocalOrderBook(sym, tick_size, market=self.market)
            self.buffers[sym] = SymbolBuffers(sym)
            self.health_state[sym] = StreamHealth(
                symbol=sym,
                market=self.market,
                connected=False,
                streams=self.connector.stream_names(sym),
                status="DISCONNECTED"
            )
            # Price grouping: the calibrated per-symbol increment (falling back to the
            # raw exchange tick) keeps the footprint at a readable row count.
            base_group = settings.flow_tick_group_base(sym, tick_size)
            tick_group = base_group * settings.FLOW_TICK_GROUP_MULTIPLIER
            if tick_group <= 0: tick_group = tick_size
            self.footprint_engines[sym] = {
                interval: FootprintEngine(sym, interval, tick_group)
                for interval in settings.FLOW_FOOTPRINT_INTERVALS
            }
            # Aggregation engines (each multiplies tick_size by FLOW_TICK_GROUP_MULTIPLIER)
            self.delta_engines[sym] = DeltaEngine(sym)
            self.profile_engines[sym] = VolumeProfileEngine(sym, base_group)
            self.heatmap_engines[sym] = HeatmapEngine(sym, base_group)
            # The ladder needs a far finer grouping than the footprint: at the footprint
            # increment BTC's top-of-book would collapse into a couple of rows.
            self.dom_engines[sym] = DomEngine(sym, max(tick_size, base_group / 100.0))
            self.tape_engines[sym] = TapeEngine()

    def _stream_groups(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        for sym in self.books:
            for base_url, streams in self.connector.stream_groups(sym).items():
                groups.setdefault(base_url, []).extend(streams)
        return groups

    def _drop_symbol(self, sym: str) -> None:
        for registry in (self.books, self.buffers, self.health_state, self.footprint_engines,
                         self.delta_engines, self.profile_engines, self.heatmap_engines,
                         self.dom_engines, self.tape_engines, self._msg_counters):
            registry.pop(sym, None)
        self.connector.symbol_filters.pop(sym, None)

    async def subscribe(self, symbol: str) -> None:
        """Reserve bounded demand, initialize the symbol, and begin real ingestion."""
        sym = self.connector.normalize_symbol(symbol)
        if not sym.isalnum() or len(sym) > 30:
            raise ValueError("Invalid symbol")
        async with self._subscription_lock:
            if not settings.FLOW_ENABLED:
                raise ValueError("Order flow is disabled")
            pinned = sym in self.pinned_symbols or (self.market == "spot" and sym in settings.FLOW_SYMBOLS)
            if sym not in self.dynamic_subs and not pinned:
                active = sum(sum(s not in h.pinned_symbols for s in h.dynamic_subs) for h in _hubs.values())
                if active >= settings.FLOW_MAX_ACTIVE_SYMBOLS:
                    raise ValueError("Active order-flow symbol limit reached")
            self.dynamic_subs[sym] = self.dynamic_subs.get(sym, 0) + 1
            try:
                await self.start()
                if sym not in self.books:
                    await self._init_symbol_state(sym)
                    await self.stream_manager.update_streams(self._stream_groups())
            except BaseException:
                self.dynamic_subs[sym] -= 1
                if self.dynamic_subs[sym] <= 0:
                    self.dynamic_subs.pop(sym, None)
                    if sym not in self.pinned_symbols:
                        self._drop_symbol(sym)
                raise

    async def unsubscribe(self, symbol: str) -> None:
        """Release one demand owner and discard idle non-pinned stream state."""
        sym = self.connector.normalize_symbol(symbol)
        async with self._subscription_lock:
            count = self.dynamic_subs.get(sym, 0)
            if count > 1:
                self.dynamic_subs[sym] = count - 1
                return
            self.dynamic_subs.pop(sym, None)
            if sym in self.pinned_symbols or sym not in self.books:
                return
            task = self._resync_by_symbol.pop(sym, None)
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            self._drop_symbol(sym)
            await self.stream_manager.update_streams(self._stream_groups())

    def get_state(self, symbol: str) -> Optional[dict]:
        sym = self.connector.normalize_symbol(symbol)
        if sym not in self.books:
            return None
        return {
            "book": self.books[sym],
            "buffers": self.buffers[sym],
            "health": self.health()[sym]
        }
        
    def _sample_heatmap(self, sym: str, event_time: int):
        """Append one resting-liquidity frame per time bin for the heatmap panel."""
        engine = self.heatmap_engines.get(sym)
        if engine is None:
            return
        bin_ms = max(1, engine.bin_ms)
        if (event_time // bin_ms) * bin_ms == engine.last_bin_ts:
            return
        book = self.books.get(sym)
        if book is None:
            return
        engine.process_book(book.get_snapshot(200))

    def get_dom(self, symbol: str, levels: int = 20):
        """Compute live depth-of-market analytics from the maintained book."""
        sym = self.connector.normalize_symbol(symbol)
        engine = self.dom_engines.get(sym)
        book = self.books.get(sym)
        if engine is None or book is None:
            return None
        now_ms = int(time.time() * 1000)
        trades_1m = []
        for t in reversed(self.buffers[sym].trades):
            if t.ts <= now_ms - 60000:
                break
            trades_1m.append(t)
        trades_1m.reverse()
        # Fetch deeper than the requested ladder depth so grouping still yields N rows
        deep_levels = max(levels * 25, 500)
        return engine.compute_analytics(book.get_snapshot(deep_levels), trades_1m)

    def get_heatmap_snapshot(self, symbol: str):
        """Return the historical resting-liquidity matrix for a symbol."""
        sym = self.connector.normalize_symbol(symbol)
        engine = self.heatmap_engines.get(sym)
        if engine is None:
            return None
        return engine.get_snapshot()

    def get_volume_profile(
        self,
        symbol: str,
        mode: Literal["SESSION", "VISIBLE", "FIXED_RANGE"] = "SESSION",
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        tick_group: Optional[float] = None
    ):
        """Return a delta-aware volume profile for the session or an explicit range."""
        sym = self.connector.normalize_symbol(symbol)
        if sym not in self.buffers:
            return None
        engine = self.profile_engines.get(sym)
        now_ms = int(time.time() * 1000)
        if mode == "SESSION" and engine is not None:
            return engine.get_session_profile(now_ms)

        from backend.engine.volume_profile import compute_profile_from_trades
        group = tick_group or (engine.tick_group if engine else self.books[sym].tick_size)
        range_start = start_ts or (self.buffers[sym].trades[0].ts if self.buffers[sym].trades else now_ms)
        range_end = end_ts or now_ms
        trades = [t for t in self.buffers[sym].trades if range_start <= t.ts <= range_end]
        return compute_profile_from_trades(sym, trades, mode, range_start, range_end, group)

    def get_cvd(self, symbol: str, limit: int = 240):
        """Return the recent CVD time series for the delta panel."""
        sym = self.connector.normalize_symbol(symbol)
        engine = self.delta_engines.get(sym)
        if engine is None:
            return []
        # Prefer the fine-grained trailing-minute line; fall back to the 1-minute
        # history points while the trade buffer is still warming up.
        series = engine.get_recent_cvd_series(buckets=min(60, max(2, limit)))
        if len(series) >= 2:
            return series
        return list(engine.cvd_history)[-limit:]

    def get_metrics(self, symbol: str) -> Optional[FlowMetrics]:
        """Build the live FlowMetrics snapshot consumed by the UI and the trading agents."""
        sym = self.connector.normalize_symbol(symbol)
        if sym not in self.health_state:
            return None

        health = self.health()[sym]
        now_ms = int(time.time() * 1000)
        delta = self.delta_engines.get(sym)
        profile = self.profile_engines.get(sym)
        dom = self.get_dom(sym, settings.FLOW_DEPTH_LEVELS)

        delta_metrics = delta.get_metrics() if delta else {}
        vwap, vwap_up, vwap_dn = delta.get_vwap() if delta else (0.0, 0.0, 0.0)

        intervals = settings.FLOW_FOOTPRINT_INTERVALS
        bars = self.get_footprint_bars(sym, intervals[0], limit=1) if intervals else []
        bar = bars[-1] if bars else None

        poc = vah = val = 0.0
        if profile is not None:
            snap = profile.get_session_profile(now_ms)
            poc, vah, val = snap.poc_price, snap.vah, snap.val
        if bar is not None:
            poc, vah, val = bar.poc_price, bar.vah, bar.val

        price = self.buffers[sym].trades[-1].price if self.buffers[sym].trades else 0.0

        price_vs_value = "IN_VALUE"
        if price and vah and val:
            if price > vah:
                price_vs_value = "ABOVE_VALUE"
            elif price < val:
                price_vs_value = "BELOW_VALUE"

        walls = dom.walls if dom is not None else []
        nearest_bid_wall = None
        nearest_ask_wall = None
        if price:
            below = [w.get("price", 0.0) for w in walls if w.get("side") == "BID" and w.get("price", 0.0) < price]
            above = [w.get("price", 0.0) for w in walls if w.get("side") == "ASK" and w.get("price", 0.0) > price]
            nearest_bid_wall = max(below) if below else None
            nearest_ask_wall = min(above) if above else None

        # Rolling 1-second activity (walk back from the newest print and stop early)
        cutoff = now_ms - 1000
        trade_rate = 0.0
        volume_rate = 0.0
        for t in reversed(self.buffers[sym].trades):
            if t.ts <= cutoff:
                break
            trade_rate += 1.0
            volume_rate += t.qty

        stacked_bias = "NEUTRAL"
        if bar is not None:
            if bar.stacked_buy_imbalance_zones:
                stacked_bias = "BUY"
            elif bar.stacked_sell_imbalance_zones:
                stacked_bias = "SELL"

        return FlowMetrics(
            symbol=sym,
            ts=now_ms,
            price=price,
            session_cvd=float(delta_metrics.get("session_cvd", 0.0)),
            bar_delta=bar.delta if bar is not None else 0.0,
            delta_percent=bar.delta_percent if bar is not None else 0.0,
            cvd_slope=float(delta_metrics.get("cvd_slope", 0.0)),
            cvd_divergence=delta_metrics.get("cvd_divergence"),
            buy_sell_ratio=float(delta_metrics.get("buy_sell_ratio", 1.0)),
            aggression_index=float(delta_metrics.get("aggression_index", 0.0)),
            absorption_flag=bar.absorption if bar is not None else None,
            stacked_imbalance_bias=stacked_bias,
            poc_price=poc,
            vah=vah,
            val=val,
            price_vs_value=price_vs_value,
            book_imbalance=dom.book_imbalance if dom is not None else 0.0,
            spread_bps=dom.spread_bps if dom is not None else 0.0,
            nearest_bid_wall=nearest_bid_wall,
            nearest_ask_wall=nearest_ask_wall,
            vwap=vwap,
            vwap_upper_1=vwap_up,
            vwap_lower_1=vwap_dn,
            trade_rate=trade_rate,
            volume_rate=volume_rate,
            health=health
        )
        
    def get_footprint_bars(self, symbol: str, interval: str = "1m", limit: int = 240):
        """Helper for auto_trader to fetch footprint bars."""
        sym = self.connector.normalize_symbol(symbol)
        if sym not in self.buffers:
            return []
        bars_deque = self.buffers[sym].bars.get(interval, [])
        bars = list(bars_deque)[-max(1, min(limit, 240)):]
        engine = self.footprint_engines.get(sym, {}).get(interval)
        if bars and engine and engine.current_bar is bars[-1]:
            # Materialize forming cells only when a fixed-rate reader requests them.
            bars[-1] = bars[-1].model_copy(update={"cells": sorted(engine.cells_dict.values(), key=lambda c: c.price)})
        return [self._bounded_footprint(bar) for bar in bars]

    def _bounded_footprint(self, bar):
        """Coarsen real volume for at most 512 displayed rows, preserving OHLC."""
        if bar.high - bar.low <= 512 * bar.tick_group:
            return bar
        group = math.ceil((bar.high - bar.low) / (512 * bar.tick_group)) * bar.tick_group
        cells = {}
        for cell in bar.cells:
            price = round(math.floor(cell.price / group) * group, 8)
            if price not in cells:
                cells[price] = cell.model_copy(update={"price": price})
                continue
            target = cells[price]
            for field in ("buy_volume", "sell_volume", "total_volume", "delta", "trades"):
                setattr(target, field, getattr(target, field) + getattr(cell, field))
            target.buy_imbalance |= cell.buy_imbalance
            target.sell_imbalance |= cell.sell_imbalance
        return bar.model_copy(update={"tick_group": group, "cells": sorted(cells.values(), key=lambda c: c.price)})

    def register_listener(self, callback: Callable[[str, Any], None]):
        self.listeners.append(callback)

    def health(self) -> Dict[str, StreamHealth]:
        """Derive freshness from both actual trade receipt and synchronized depth."""
        now = int(time.time() * 1000)
        for sym, health in self.health_state.items():
            if health.status == "DEGRADED" and not self.books[sym].is_synced:
                continue
            if not health.last_trade_ts or not health.last_book_ts:
                health.status = "WAITING" if health.connected else "DISCONNECTED"
            elif now - min(health.last_trade_ts, health.last_book_ts) > settings.FLOW_STALE_AFTER_MS:
                health.status = "STALE"
                health.connected = False
            elif not self.books[sym].is_synced:
                health.status = "WAITING"
            else:
                health.status = "LIVE"
        return self.health_state

    def _trigger_resync(self, symbol: str) -> None:
        """Schedule at most one bounded snapshot task per symbol."""
        sym = self.connector.normalize_symbol(symbol)
        if sym in self.books and sym not in self._resync_by_symbol:
            book = self.books[sym]
            if book.is_synced:
                book._event_buffer.clear()
            book.is_synced = False
            task = asyncio.create_task(self._do_resync(sym))
            self._resync_tasks.add(task)
            self._resync_by_symbol[sym] = task
            def finished(done: asyncio.Task) -> None:
                self._resync_tasks.discard(done)
                if self._resync_by_symbol.get(sym) is done:
                    self._resync_by_symbol.pop(sym, None)
            task.add_done_callback(finished)

    async def _do_resync(self, sym: str):
        book = self.books[sym]
        health = self.health_state[sym]
        
        # Backoff: never snapshot more than once every 5s per symbol
        now = time.time()
        if now - book.last_sync_attempt_ts < 5.0:
            return
            
        book.last_sync_attempt_ts = now
        book.is_syncing = True
        
        try:
            snapshot = await self.connector.depth_snapshot(sym, settings.FLOW_DEPTH_SNAPSHOT_LIMIT)
            success = book.process_snapshot(snapshot)
            if success:
                health.book_resyncs += 1
                self.health()
                logger.info(f"[{sym}] Order book resynced successfully.")
            else:
                logger.warning(f"[{sym}] Resync snapshot could not be applied against event buffer.")
        except Exception as e:
            import httpx
            if isinstance(e, httpx.HTTPStatusError):
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get("Retry-After", "60"))
                    logger.warning(f"[{sym}] Rate limited (429). Backing off for {retry_after}s.")
                    book.last_sync_attempt_ts = now + retry_after - 5.0 # ensure wait
                elif e.response.status_code == 418:
                    logger.error(f"[{sym}] IP Banned (418). Marking DEGRADED.")
                    health.status = "DEGRADED"
                    book.last_sync_attempt_ts = now + 86400 # wait a day
                else:
                    logger.error(f"[{sym}] Book resync failed with HTTP error: {e}")
            else:
                logger.error(f"[{sym}] Book resync failed: {e}")
        finally:
            book.is_syncing = False

    def _on_message(self, raw: dict[str, Any]):
        try:
            parsed = self.connector.parse(raw)
            if not parsed:
                return

            event_time = int(time.time() * 1000)

            # Determine symbol
            sym = None
            if hasattr(parsed, 'symbol'):
                sym = parsed.symbol
            elif isinstance(parsed, dict) and 's' in parsed:
                sym = parsed['s']
            
            if not sym:
                return
                
            sym = self.connector.normalize_symbol(sym)
            
            if sym not in self.books:
                return

            self._msg_counters[sym] = self._msg_counters.get(sym, 0) + 1

            health = self.health_state[sym]
            health.connected = True
            
            from backend.marketdata.models import Trade, BookDelta
            
            if isinstance(parsed, Trade):
                if not self.buffers[sym].trades and sym not in settings.FLOW_TICK_GROUP_DEFAULTS:
                    # Derive a readable increment from a real first print, never a fake price.
                    tick = self.books[sym].tick_size
                    base = max(tick, math.ceil(parsed.price * .0001 / tick) * tick)
                    for engine in [*self.footprint_engines[sym].values(), self.profile_engines[sym], self.heatmap_engines[sym]]:
                        engine.tick_group = base * settings.FLOW_TICK_GROUP_MULTIPLIER
                    self.dom_engines[sym].tick_group = max(tick, base / 100) * settings.FLOW_TICK_GROUP_MULTIPLIER
                self.buffers[sym].add_trade(parsed)
                self.buffers[sym].tape.append(self.tape_engines[sym].process_trade(parsed))
                if sym in self.delta_engines:
                    self.delta_engines[sym].process_trade(parsed)
                if sym in self.profile_engines:
                    self.profile_engines[sym].process_trade(parsed)
                health.last_trade_ts = parsed.ts
                # Clamp at zero: a negative figure only means the local clock trails
                # the exchange, and showing it as \"lag\" is misleading.
                health.lag_ms = max(0, event_time - parsed.ts)
                health.gap_events = self.buffers[sym].trade_gaps
                
                # Process footprint
                if sym in self.footprint_engines:
                    for interval, engine in self.footprint_engines[sym].items():
                        closed_bar, current_bar = engine.process_trade(parsed)
                        bars_deque = self.buffers[sym].bars[interval]
                        if len(bars_deque) == 0:
                            bars_deque.append(current_bar)
                        else:
                            if bars_deque[-1].open_time == current_bar.open_time:
                                bars_deque[-1] = current_bar
                            else:
                                bars_deque.append(current_bar)
            elif isinstance(parsed, BookDelta):
                success = self.books[sym].process_diff(parsed)
                if not success and not self.books[sym].is_syncing:
                    health.status = "DEGRADED"
                    health.gap_events += 1
                    self._trigger_resync(sym)
                health.last_book_ts = parsed.event_ts
                if self.books[sym].is_synced:
                    self._sample_heatmap(sym, event_time)
            elif isinstance(parsed, dict):
                if 'k' in parsed and 'x' in parsed['k']:
                    # Kline
                    pass
                elif 'bids' in parsed and 'lastUpdateId' in parsed:
                    # Partial book
                    self.books[sym].apply_partial(parsed)
                    self._sample_heatmap(sym, event_time)
                    
            # Fan out to listeners (e.g. aggregators)
            for listener in self.listeners:
                listener(sym, parsed)

        except Exception as e:
            logger.error(f"Error processing websocket message: {e}")

hub = MarketDataHub()
_hubs: dict[str, MarketDataHub] = {"spot": hub}


def get_hub(market: str = "spot") -> MarketDataHub:
    """Resolve one isolated market hub, preserving the existing Spot default."""
    if market not in ("spot", "futures"):
        raise ValueError("market must be spot or futures")
    if market not in _hubs:
        _hubs[market] = MarketDataHub(market)
    return _hubs[market]


async def stop_hubs() -> None:
    """Await every market's tasks at application shutdown."""
    await asyncio.gather(*(h.stop() for h in _hubs.values()))
