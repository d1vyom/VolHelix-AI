import asyncio
import time
from typing import Dict, Callable, Any, Optional
from loguru import logger

from backend.config import settings
from backend.marketdata.models import StreamHealth
from backend.marketdata.buffers import SymbolBuffers
from backend.marketdata.orderbook import LocalOrderBook
from backend.marketdata.stream_manager import StreamManager
from backend.marketdata.connectors.binance_spot import BinanceSpotConnector

class MarketDataHub:
    """Singleton registry and pub/sub hub for all market data."""
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(MarketDataHub, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        
        self.connector = BinanceSpotConnector()
        self.stream_manager = StreamManager(callback=self._on_message, trigger_resync=self._trigger_resync)
        
        self.buffers: Dict[str, SymbolBuffers] = {}
        self.books: Dict[str, LocalOrderBook] = {}
        self.health_state: Dict[str, StreamHealth] = {}
        
        self.listeners: list[Callable[[str, Any], None]] = []
        self.dynamic_subs: Dict[str, int] = {} # symbol -> refcount
        
        self._resync_tasks: set[asyncio.Task] = set()
        self._running = False
        
    async def start(self):
        """Starts the hub and websocket ingestion."""
        if not settings.FLOW_ENABLED:
            logger.info("MarketDataHub is disabled by configuration.")
            return
            
        self._running = True
        logger.info("MarketDataHub starting...")
        
        # Init state for static symbols
        for sym in settings.FLOW_SYMBOLS:
            await self._init_symbol_state(sym)
            
        # build streams
        streams = []
        for sym in self.books.keys():
            streams.extend(self.connector.stream_names(sym))
            
        await self.stream_manager.start(streams)

    async def stop(self):
        """Stops ingestion and cleans up."""
        self._running = False
        await self.stream_manager.stop()
        for task in self._resync_tasks:
            task.cancel()
        self._resync_tasks.clear()

    async def _init_symbol_state(self, symbol: str):
        sym = self.connector.normalize_symbol(symbol)
        if sym not in self.books:
            tick_size = await self.connector.tick_size(sym)
            self.books[sym] = LocalOrderBook(sym, tick_size)
            self.buffers[sym] = SymbolBuffers(sym)
            self.health_state[sym] = StreamHealth(
                symbol=sym,
                connected=False,
                streams=self.connector.stream_names(sym),
                status="DISCONNECTED"
            )

    def subscribe(self, symbol: str):
        sym = self.connector.normalize_symbol(symbol)
        self.dynamic_subs[sym] = self.dynamic_subs.get(sym, 0) + 1
        # TODO: if not in books, init state and subscribe dynamically via stream_manager

    def unsubscribe(self, symbol: str):
        sym = self.connector.normalize_symbol(symbol)
        if sym in self.dynamic_subs:
            self.dynamic_subs[sym] -= 1
            if self.dynamic_subs[sym] <= 0:
                del self.dynamic_subs[sym]
                # TODO: unsubscribe from stream_manager if not in FLOW_SYMBOLS

    def get_state(self, symbol: str) -> Optional[dict]:
        sym = self.connector.normalize_symbol(symbol)
        if sym not in self.books:
            return None
        return {
            "book": self.books[sym],
            "buffers": self.buffers[sym],
            "health": self.health_state[sym]
        }

    def register_listener(self, callback: Callable[[str, Any], None]):
        self.listeners.append(callback)

    def health(self) -> Dict[str, StreamHealth]:
        return self.health_state

    def _trigger_resync(self, symbol: str):
        sym = self.connector.normalize_symbol(symbol)
        if sym in self.books:
            # We must not block the event loop with a REST request, so we create a task
            task = asyncio.create_task(self._do_resync(sym))
            self._resync_tasks.add(task)
            task.add_done_callback(self._resync_tasks.discard)

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
                health.status = "LIVE"
                logger.info(f"[{sym}] Order book resynced successfully.")
            else:
                logger.warning(f"[{sym}] Resync snapshot could not be applied against event buffer.")
        except Exception as e:
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

            health = self.health_state[sym]
            health.connected = True
            
            from backend.marketdata.models import Trade, BookDelta
            
            if isinstance(parsed, Trade):
                self.buffers[sym].add_trade(parsed)
                health.last_trade_ts = parsed.ts
                health.lag_ms = event_time - parsed.ts
                health.gap_events = self.buffers[sym].trade_gaps
            elif isinstance(parsed, BookDelta):
                success = self.books[sym].process_diff(parsed)
                if not success and not self.books[sym].is_syncing:
                    health.status = "DEGRADED"
                    health.gap_events += 1
                    self._trigger_resync(sym)
                health.last_book_ts = parsed.event_ts
            elif isinstance(parsed, dict):
                if 'k' in parsed and 'x' in parsed['k']:
                    # Kline
                    pass
                elif 'bids' in parsed and 'lastUpdateId' in parsed:
                    # Partial book
                    self.books[sym].apply_partial(parsed)
                    
            # Fan out to listeners (e.g. aggregators)
            for listener in self.listeners:
                listener(sym, parsed)

        except Exception as e:
            logger.error(f"Error processing websocket message: {e}")

hub = MarketDataHub()
