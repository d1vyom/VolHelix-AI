import pytest
import time
from backend.engine.dom_analytics import DomEngine, IcebergDetector
from backend.marketdata.models import BookSnapshot

def test_dom_engine_walls_and_imbalance():
    engine = DomEngine("BTCUSDT", 1.0)
    
    bids = [(100.0, 10.0), (99.0, 10.0), (90.0, 500.0)] # 90 is a wall
    asks = [(101.0, 10.0), (102.0, 10.0), (110.0, 10.0)]
    
    book = BookSnapshot(
        symbol="BTCUSDT",
        last_update_id=1,
        bids=bids,
        asks=asks,
        ts=1000,
        source="REST"
    )
    
    analytics = engine.compute_analytics(book, [])
    
    assert len(analytics.walls) == 1
    assert analytics.walls[0]['price'] == 90.0
    assert analytics.walls[0]['side'] == "BID"
    
    # Imbalance: bids sum = 520, asks sum = 30
    # Imbalance = (520 - 30) / (520 + 30) = 490 / 550 = 0.89
    assert round(analytics.book_imbalance, 2) == 0.89
    
def test_iceberg_detector():
    detector = IcebergDetector()
    ts = 1000
    
    # Level at 100 drops and refills
    detector.update_book({100.0: 100.0}, {}, ts)
    
    # Drops
    detector.update_book({100.0: 10.0}, {}, ts + 1000)
    # Refills
    detector.update_book({100.0: 100.0}, {}, ts + 2000)
    
    # Drops
    detector.update_book({100.0: 10.0}, {}, ts + 3000)
    # Refills
    detector.update_book({100.0: 100.0}, {}, ts + 4000)
    
    # Drops
    detector.update_book({100.0: 10.0}, {}, ts + 5000)
    # Refills
    detector.update_book({100.0: 100.0}, {}, ts + 6000)
    
    assert detector.is_iceberg(100.0) is True
