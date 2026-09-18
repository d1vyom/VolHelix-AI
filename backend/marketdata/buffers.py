import collections
from typing import Dict
from backend.marketdata.models import Trade
from backend.engine.flow_models import HeatmapFrame, TapeEntry, FootprintBar
from backend.config import settings

class SymbolBuffers:
    """Bounded ring buffers for a single symbol."""
    def __init__(self, symbol: str):
        self.symbol = symbol.upper()
        
        # Raw trades
        self.trades: collections.deque[Trade] = collections.deque(maxlen=settings.FLOW_TRADE_BUFFER)
        
        # Tape entries
        self.tape: collections.deque[TapeEntry] = collections.deque(maxlen=settings.FLOW_TAPE_BUFFER)
        
        # Heatmap frames
        heatmap_capacity = (settings.FLOW_HEATMAP_WINDOW_SEC * 1000) // settings.FLOW_HEATMAP_BIN_MS
        self.heatmap: collections.deque[HeatmapFrame] = collections.deque(maxlen=heatmap_capacity)
        
        # Footprint bars per interval
        self.bars: Dict[str, collections.deque[FootprintBar]] = {
            interval: collections.deque(maxlen=settings.FLOW_FOOTPRINT_BARS)
            for interval in settings.FLOW_FOOTPRINT_INTERVALS
        }
        
        # Gap tracking
        self.trade_gaps: int = 0
        self.previous_agg_id: int | None = None

    def add_trade(self, trade: Trade):
        """Append trade and detect sequence gaps."""
        if self.previous_agg_id is not None:
            # Trade gap detection logic
            # A new agg_id should be strictly greater. Usually +1. 
            # If it's more than +1, we might have missed one or more trades.
            if trade.agg_id > self.previous_agg_id + 1:
                self.trade_gaps += 1
        
        self.previous_agg_id = trade.agg_id
        self.trades.append(trade)

