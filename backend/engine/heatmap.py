import time
import numpy as np
from typing import Dict
from collections import deque
from backend.marketdata.models import BookSnapshot
from backend.engine.flow_models import HeatmapFrame, HeatmapSnapshot
from backend.engine.footprint import round_to_tick
from backend.config import settings

class HeatmapEngine:
    def __init__(self, symbol: str, tick_size: float):
        self.symbol = symbol.upper()
        self.tick_group = tick_size * settings.FLOW_TICK_GROUP_MULTIPLIER
        self.bin_ms = settings.FLOW_HEATMAP_BIN_MS
        self.window_sec = settings.FLOW_HEATMAP_WINDOW_SEC
        
        self.max_frames = int((self.window_sec * 1000) / max(self.bin_ms, 1))
        self.frames = deque(maxlen=max(1, self.max_frames))
        self.last_bin_ts = 0

    def process_book(self, book: BookSnapshot) -> HeatmapFrame | None:
        now = int(time.time() * 1000)
        bin_ts = (now // self.bin_ms) * self.bin_ms
        
        if bin_ts == self.last_bin_ts:
            return None
            
        self.last_bin_ts = bin_ts
        
        bids: Dict[float, float] = {}
        asks: Dict[float, float] = {}
        
        for p, s in book.bids:
            bucket = round_to_tick(p, self.tick_group)
            bids[bucket] = bids.get(bucket, 0.0) + s
            
        for p, s in book.asks:
            bucket = round_to_tick(p, self.tick_group)
            asks[bucket] = asks.get(bucket, 0.0) + s
            
        best_bid = max(bids.keys()) if bids else 0.0
        best_ask = min(asks.keys()) if asks else 0.0
        mid = (best_bid + best_ask) / 2.0 if best_bid and best_ask else (best_bid or best_ask)
        
        K = 60
        min_p = mid - (K * self.tick_group)
        max_p = mid + (K * self.tick_group)
        
        merged = {}
        for p, s in bids.items():
            if min_p <= p <= max_p:
                merged[p] = [p, s, 0.0]
                
        for p, s in asks.items():
            if min_p <= p <= max_p:
                if p in merged:
                    merged[p][2] += s
                else:
                    merged[p] = [p, 0.0, s]
                    
        frame = HeatmapFrame(
            ts_bin=bin_ts,
            levels=list(merged.values())
        )
        self.frames.append(frame)
        return frame

    def get_snapshot(self) -> HeatmapSnapshot:
        if not self.frames:
            return HeatmapSnapshot(
                symbol=self.symbol,
                tick_group=self.tick_group,
                bin_ms=self.bin_ms,
                window_sec=self.window_sec,
                price_min=0.0,
                price_max=0.0,
                max_size=0.0,
                frames=[],
                walls=[]
            )
            
        all_sizes = []
        price_min = float('inf')
        price_max = float('-inf')
        
        for f in self.frames:
            for lvl in f.levels:
                p, bs, as_ = lvl
                all_sizes.append(bs + as_)
                price_min = min(price_min, p)
                price_max = max(price_max, p)
                
        max_size = 0.0
        if all_sizes:
            max_size = float(np.percentile(all_sizes, 99))
            
        if price_min == float('inf'):
            price_min = 0.0
        if price_max == float('-inf'):
            price_max = 0.0
            
        return HeatmapSnapshot(
            symbol=self.symbol,
            tick_group=self.tick_group,
            bin_ms=self.bin_ms,
            window_sec=self.window_sec,
            price_min=price_min,
            price_max=price_max,
            max_size=max_size,
            frames=list(self.frames),
            walls=[]
        )
