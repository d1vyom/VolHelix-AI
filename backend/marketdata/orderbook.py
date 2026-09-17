import time
import math
from typing import Dict, List, Tuple
from collections import deque
from backend.marketdata.models import BookDelta, BookSnapshot, LadderLevel
from backend.config import settings

class LocalOrderBook:
    """Maintains a local L2 order book using diff-depth updates and snapshots."""
    def __init__(self, symbol: str, tick_size: float):
        self.symbol = symbol.upper()
        self.tick_size = tick_size
        
        # Bids/Asks dictionaries (price -> qty)
        self.bids: Dict[float, float] = {}
        self.asks: Dict[float, float] = {}
        self.last_update_id: int | None = None
        
        # Sync state
        self.is_synced = False
        self.is_syncing = False
        self._event_buffer: deque[BookDelta] = deque(maxlen=200)
        self.last_sync_attempt_ts = 0.0
        
        # Fallback partial book
        self.partial_bids: Dict[float, float] = {}
        self.partial_asks: Dict[float, float] = {}

    def apply_partial(self, data: dict):
        """Apply partial depth from @depth20 stream (no sync needed)."""
        # Binance sends strings for prices and quantities
        self.partial_bids = {float(p): float(q) for p, q in data.get("bids", [])}
        self.partial_asks = {float(p): float(q) for p, q in data.get("asks", [])}

    def process_diff(self, delta: BookDelta) -> bool:
        """
        Process a diff depth update.
        Returns True if successfully applied, False if gap detected or not synced.
        """
        if not self.is_synced:
            self._event_buffer.append(delta)
            return False

        if self.last_update_id is None:
            return False
            
        if delta.first_update_id != self.last_update_id + 1:
            self.is_synced = False
            return False

        self._apply_updates(delta.bids, delta.asks)
        self.last_update_id = delta.final_update_id
        return True

    def process_snapshot(self, snapshot: BookSnapshot) -> bool:
        """
        Attempt to sync using a fetched snapshot and the event buffer.
        Returns True if successful, False if buffer didn't contain matching sequence.
        """
        self.is_syncing = False
        
        # Drop older events
        while self._event_buffer and self._event_buffer[0].final_update_id <= snapshot.last_update_id:
            self._event_buffer.popleft()
            
        if not self._event_buffer:
            return False
            
        first_event = self._event_buffer[0]
        if not (first_event.first_update_id <= snapshot.last_update_id + 1 <= first_event.final_update_id):
            return False
            
        # Clear book and apply snapshot
        self.bids = {p: q for p, q in snapshot.bids}
        self.asks = {p: q for p, q in snapshot.asks}
        self.last_update_id = snapshot.last_update_id
        self.is_synced = True
        
        # The first event overlaps with the snapshot, apply directly
        first_event = self._event_buffer.popleft()
        self._apply_updates(first_event.bids, first_event.asks)
        self.last_update_id = first_event.final_update_id
        
        # Apply remaining buffered events
        for delta in list(self._event_buffer):
            if not self.process_diff(delta):
                return False
                
        self._event_buffer.clear()
        return True

    def _apply_updates(self, bids: List[List[float]], asks: List[List[float]]):
        for p, q in bids:
            if q == 0.0:
                self.bids.pop(p, None)
            else:
                self.bids[p] = q
                
        for p, q in asks:
            if q == 0.0:
                self.asks.pop(p, None)
            else:
                self.asks[p] = q

    def get_ladder(self, levels: int = 20, tick_group_multiplier: float = 1.0) -> list[LadderLevel]:
        """Project the book into a ladder."""
        bucket_size = self.tick_size * tick_group_multiplier
        
        bids_src = self.bids if self.is_synced and settings.FLOW_USE_DIFF_DEPTH else self.partial_bids
        asks_src = self.asks if self.is_synced and settings.FLOW_USE_DIFF_DEPTH else self.partial_asks
        
        grouped_bids: Dict[float, float] = {}
        for p, q in bids_src.items():
            bucket = math.floor(p / bucket_size) * bucket_size
            # round to fix floating point issues
            bucket = round(bucket, 8)
            grouped_bids[bucket] = grouped_bids.get(bucket, 0.0) + q
            
        grouped_asks: Dict[float, float] = {}
        for p, q in asks_src.items():
            bucket = math.ceil(p / bucket_size) * bucket_size
            bucket = round(bucket, 8)
            grouped_asks[bucket] = grouped_asks.get(bucket, 0.0) + q

        sorted_bids = sorted(grouped_bids.items(), key=lambda x: x[0], reverse=True)[:levels]
        sorted_asks = sorted(grouped_asks.items(), key=lambda x: x[0])[:levels]

        # Combine into ladder levels
        ladder_levels: Dict[float, LadderLevel] = {}
        
        for p, q in sorted_bids:
            ladder_levels[p] = LadderLevel(price=p, bid_size=q, bid_notional=p*q)
            
        for p, q in sorted_asks:
            if p in ladder_levels:
                ladder_levels[p].ask_size = q
                ladder_levels[p].ask_notional = p * q
            else:
                ladder_levels[p] = LadderLevel(price=p, ask_size=q, ask_notional=p*q)
                
        # Calculate depth_pct
        max_size = 0.0
        for ll in ladder_levels.values():
            if ll.bid_size > max_size: max_size = ll.bid_size
            if ll.ask_size > max_size: max_size = ll.ask_size
            
        if max_size > 0:
            for ll in ladder_levels.values():
                ll.depth_pct = max(ll.bid_size, ll.ask_size) / max_size
                
        return sorted(list(ladder_levels.values()), key=lambda x: x.price, reverse=True)

    def get_top_of_book(self) -> Tuple[float, float]:
        """Returns best_bid, best_ask."""
        bids_src = self.bids if self.is_synced and settings.FLOW_USE_DIFF_DEPTH else self.partial_bids
        asks_src = self.asks if self.is_synced and settings.FLOW_USE_DIFF_DEPTH else self.partial_asks
        
        best_bid = max(bids_src.keys()) if bids_src else 0.0
        best_ask = min(asks_src.keys()) if asks_src else 0.0
        return best_bid, best_ask

