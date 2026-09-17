import pytest
from backend.engine.heatmap import HeatmapEngine
from backend.marketdata.models import BookSnapshot

def test_heatmap_engine():
    engine = HeatmapEngine("BTCUSDT", 1.0)
    engine.bin_ms = 1000 # 1s
    
    bids = [(100.0, 10.0)]
    asks = [(101.0, 20.0)]
    
    book = BookSnapshot(
        symbol="BTCUSDT",
        last_update_id=1,
        bids=bids,
        asks=asks,
        ts=1000,
        source="REST"
    )
    
    f1 = engine.process_book(book)
    assert f1 is not None
    
    # Same bin
    f2 = engine.process_book(book)
    assert f2 is None
    
    snap = engine.get_snapshot()
    assert len(snap.frames) == 1
    assert snap.max_size > 0
    assert snap.price_min == 100.0
    assert snap.price_max == 101.0
