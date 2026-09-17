import pytest
from backend.marketdata.models import BookSnapshot, BookDelta
from backend.marketdata.orderbook import LocalOrderBook

def test_orderbook_sync_and_gap_detection():
    ob = LocalOrderBook("BTCUSDT", 0.01)
    
    # 1. Buffer a diff before snapshot
    d1 = BookDelta(
        symbol="BTCUSDT",
        first_update_id=10,
        final_update_id=12,
        bids=[[100.0, 1.0]],
        asks=[],
        event_ts=1000
    )
    res = ob.process_diff(d1)
    assert not res
    assert not ob.is_synced
    assert len(ob._event_buffer) == 1
    
    # 2. Provide a snapshot. U (10) <= lastUpdateId (10) + 1 <= u (12) is satisfied.
    snap = BookSnapshot(
        symbol="BTCUSDT",
        last_update_id=10,
        bids=[[99.0, 2.0]],
        asks=[[101.0, 2.0]],
        ts=1001,
        source="REST"
    )
    res = ob.process_snapshot(snap)
    assert res is True
    assert ob.is_synced
    assert ob.last_update_id == 12
    assert len(ob._event_buffer) == 0
    # d1 should be applied, adding a bid at 100
    assert ob.bids.get(100.0) == 1.0
    
    # 3. Apply an in-order diff removing the level
    d2 = BookDelta(
        symbol="BTCUSDT",
        first_update_id=13,
        final_update_id=15,
        bids=[[100.0, 0.0]], # qty 0 -> delete
        asks=[],
        event_ts=1002
    )
    res = ob.process_diff(d2)
    assert res is True
    assert ob.is_synced
    assert ob.last_update_id == 15
    assert 100.0 not in ob.bids
    
    # 4. Out-of-order diff (gap)
    # expected first_update_id is 16, we send 17
    d3 = BookDelta(
        symbol="BTCUSDT",
        first_update_id=17,
        final_update_id=18,
        bids=[],
        asks=[],
        event_ts=1003
    )
    res = ob.process_diff(d3)
    assert res is False
    assert not ob.is_synced
