import asyncio
import json
import time
import random
from typing import Callable, Any, Dict, List, Set
from loguru import logger
import websockets
from backend.config import settings

class ConnectionChunk:
    def __init__(self, chunk_id: str, streams: List[str], callback: Callable[[dict[str, Any]], None], trigger_resync: Callable[[str], None]):
        self.chunk_id = chunk_id
        self.streams = streams
        self.callback = callback
        self.trigger_resync = trigger_resync
        self.running = False
        self.task: asyncio.Task | None = None
        self.ws: websockets.WebSocketClientProtocol | None = None
        self.reconnects = 0

    async def start(self):
        self.running = True
        self.task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        if self.ws:
            await self.ws.close()

    async def _run_loop(self):
        stream_str = "/".join(self.streams)
        url = f"{settings.FLOW_WS_BASE_URL}/stream?streams={stream_str}"
        backoff = 1

        while self.running:
            try:
                logger.info(f"Connecting to Binance WS for chunk {self.chunk_id}...")
                async with websockets.connect(url, ping_interval=180, ping_timeout=30) as ws:
                    self.ws = ws
                    logger.info(f"Chunk {self.chunk_id} connected.")
                    backoff = 1  # Reset backoff on successful connect
                    
                    # Trigger book resync for all symbols in this chunk
                    symbols = set(s.split('@')[0].upper() for s in self.streams)
                    for sym in symbols:
                        self.trigger_resync(sym)

                    # Rotation task
                    rotation_task = asyncio.create_task(self._rotate_after_24h())

                    try:
                        async for message in ws:
                            if not self.running:
                                break
                            data = json.loads(message)
                            self.callback(data)
                    finally:
                        rotation_task.cancel()
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self.running:
                    break
                self.reconnects += 1
                jitter = random.uniform(0.8, 1.2)
                sleep_time = min(backoff * jitter, settings.FLOW_MAX_RECONNECT_BACKOFF_SEC)
                logger.error(f"WS Chunk {self.chunk_id} disconnected: {e}. Reconnecting in {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
                backoff *= 2

    async def _rotate_after_24h(self):
        # Reconnect slightly before 24h (e.g., 23.5 hours)
        await asyncio.sleep(23.5 * 3600)
        logger.info(f"Chunk {self.chunk_id} rotating connection after 23.5h")
        if self.ws and self.running:
            # Closing the socket will break the async for loop and cause a reconnect without backoff
            await self.ws.close()

class StreamManager:
    """Manages Binance websocket connections with multiplexing and automatic reconnects."""
    def __init__(self, callback: Callable[[dict[str, Any]], None], trigger_resync: Callable[[str], None]):
        self.callback = callback
        self.trigger_resync = trigger_resync
        self.active_chunks: Dict[str, ConnectionChunk] = {}
        self.running = False

    async def start(self, streams: List[str]):
        """Starts connections for the given streams."""
        self.running = True
        
        # Chunking: max 200 streams per connection, and group by ~5 symbols
        # A symbol has 4 streams, so 5 symbols = 20 streams. We'll just chunk every 20 streams.
        chunk_size = 20
        for i in range(0, len(streams), chunk_size):
            chunk_streams = streams[i:i+chunk_size]
            chunk_id = f"chunk_{i//chunk_size}"
            chunk = ConnectionChunk(chunk_id, chunk_streams, self.callback, self.trigger_resync)
            self.active_chunks[chunk_id] = chunk
            await chunk.start()

    async def stop(self):
        """Stops all connections."""
        self.running = False
        tasks = [chunk.stop() for chunk in self.active_chunks.values()]
        if tasks:
            await asyncio.gather(*tasks)
        self.active_chunks.clear()

    def get_reconnects(self) -> int:
        return sum(c.reconnects for c in self.active_chunks.values())
