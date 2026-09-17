import numpy as np
from typing import List
from collections import deque
from backend.marketdata.models import Trade
from backend.engine.flow_models import TapeEntry
from backend.config import settings

class TapeEngine:
    def __init__(self):
        self.notional_history = deque(maxlen=1000)
        self.last_price = 0.0
        self.last_side = None
        self.streak_count = 0
        
    def process_trade(self, trade: Trade) -> TapeEntry:
        quote_qty = trade.price * trade.qty
        
        if trade.side == self.last_side:
            self.streak_count += 1
        else:
            self.streak_count = 1
            self.last_side = trade.side
            
        if self.last_price == 0.0:
            price_tick = "SAME"
        elif trade.price > self.last_price:
            price_tick = "UP"
        elif trade.price < self.last_price:
            price_tick = "DOWN"
        else:
            price_tick = "SAME"
            
        self.last_price = trade.price
        
        size_bucket = "S"
        is_whale = False
        
        if len(self.notional_history) > 100:
            p50 = np.percentile(self.notional_history, 50)
            p90 = np.percentile(self.notional_history, 90)
            p99 = np.percentile(self.notional_history, settings.FLOW_LARGE_PRINT_PERCENTILE)
            
            if quote_qty >= p99:
                size_bucket = "XL"
                is_whale = True
            elif quote_qty >= p90:
                size_bucket = "L"
            elif quote_qty >= p50:
                size_bucket = "M"
                
        if quote_qty >= settings.FLOW_WHALE_NOTIONAL_USD:
            is_whale = True
            if size_bucket in ("S", "M", "L"):
                size_bucket = "XL"
            
        self.notional_history.append(quote_qty)
        
        return TapeEntry(
            ts=trade.ts,
            price=trade.price,
            qty=trade.qty,
            quote_qty=quote_qty,
            side=trade.side,
            is_whale=is_whale,
            size_bucket=size_bucket,
            price_tick=price_tick,
            aggressive_streak=self.streak_count
        )

def aggregate_tape(entries: List[TapeEntry], window_ms: int = 100) -> List[TapeEntry]:
    if not entries:
        return []
        
    res = []
    curr = None
    
    for e in entries:
        if curr is None:
            curr = e.model_copy()
        else:
            if e.price == curr.price and e.side == curr.side and (e.ts - curr.ts) <= window_ms:
                curr.qty += e.qty
                curr.quote_qty += e.quote_qty
                curr.is_whale = curr.is_whale or e.is_whale
                curr.aggressive_streak = max(curr.aggressive_streak, e.aggressive_streak)
                # promote size bucket if needed
                sizes = {"S": 1, "M": 2, "L": 3, "XL": 4}
                if sizes[e.size_bucket] > sizes[curr.size_bucket]:
                    curr.size_bucket = e.size_bucket
            else:
                res.append(curr)
                curr = e.model_copy()
                
    if curr is not None:
        res.append(curr)
        
    return res
