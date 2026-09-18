import asyncio
import aiosqlite
import json
from loguru import logger
from backend.config import settings

class FlowStore:
    """Optional SQLite persistence for closed footprint bars."""
    def __init__(self, db_path: str = "flow.db"):
        self.db_path = db_path
        self._batch = []
        self._lock = asyncio.Lock()
        self._task = None
        self.running = False

    async def start(self):
        if not getattr(settings, "FLOW_PERSIST_BARS", False):
            return
            
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS footprint_bars (
                    symbol TEXT,
                    interval TEXT,
                    open_time INTEGER,
                    payload_json TEXT,
                    PRIMARY KEY (symbol, interval, open_time)
                )
            """)
            await db.commit()
            
        self.running = True
        self._task = asyncio.create_task(self._flush_loop())

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._flush() # Final flush

    async def save_bar(self, symbol: str, interval: str, bar: dict):
        if not getattr(settings, "FLOW_PERSIST_BARS", False) or not bar.get("is_closed"):
            return
            
        async with self._lock:
            self._batch.append({
                "symbol": symbol,
                "interval": interval,
                "open_time": bar["open_time"],
                "payload_json": json.dumps(bar)
            })

    async def _flush_loop(self):
        while self.running:
            await asyncio.sleep(10)
            await self._flush()

    async def _flush(self):
        async with self._lock:
            if not self._batch:
                return
            batch_to_write = self._batch[:]
            self._batch.clear()
            
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.executemany(
                    "INSERT OR REPLACE INTO footprint_bars (symbol, interval, open_time, payload_json) VALUES (:symbol, :interval, :open_time, :payload_json)",
                    batch_to_write
                )
                await db.commit()
            logger.debug(f"Flushed {len(batch_to_write)} closed bars to SQLite.")
        except Exception as e:
            logger.error(f"Failed to flush flow bars to SQLite: {e}")
