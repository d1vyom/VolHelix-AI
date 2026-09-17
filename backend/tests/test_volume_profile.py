import pytest
from backend.engine.volume_profile import compute_profile_from_trades, VolumeProfileEngine
from backend.marketdata.models import Trade
from backend.config import settings

def test_volume_profile_value_area():
    settings.FLOW_VALUE_AREA_PCT = 0.7
    settings.FLOW_TICK_GROUP_MULTIPLIER = 1.0
    
    trades = [
        Trade(symbol="BTCUSDT", agg_id=1, ts=1000, price=100.0, qty=10.0, quote_qty=1000.0, side="BUY", is_buyer_maker=False, first_id=1, last_id=1),
        Trade(symbol="BTCUSDT", agg_id=2, ts=1000, price=101.0, qty=40.0, quote_qty=4040.0, side="BUY", is_buyer_maker=False, first_id=2, last_id=2), # POC
        Trade(symbol="BTCUSDT", agg_id=3, ts=1000, price=102.0, qty=20.0, quote_qty=2040.0, side="BUY", is_buyer_maker=False, first_id=3, last_id=3),
        Trade(symbol="BTCUSDT", agg_id=4, ts=1000, price=103.0, qty=30.0, quote_qty=3090.0, side="BUY", is_buyer_maker=False, first_id=4, last_id=4),
        Trade(symbol="BTCUSDT", agg_id=5, ts=1000, price=104.0, qty=5.0, quote_qty=520.0, side="BUY", is_buyer_maker=False, first_id=5, last_id=5),
    ]
    # total vol = 105. 70% = 73.5
    # POC = 101 (vol 40). VA = 40.
    # two above (102, 103) = 50. two below (100) = 10.
    # 50 > 10, so adds 102 and 103.
    # VA now = 40 + 50 = 90. 90 >= 73.5, stop.
    # VAH = 103, VAL = 101.
    
    prof = compute_profile_from_trades("BTCUSDT", trades, "VISIBLE", 0, 2000, 1.0)
    
    assert prof.poc_price == 101.0
    assert prof.vah == 103.0
    assert prof.val == 101.0

def test_volume_profile_naked_poc():
    engine = VolumeProfileEngine("BTCUSDT", 1.0)
    engine.add_naked_poc(105.0)
    engine.add_naked_poc(110.0)
    
    # Trade at 105 removes it
    t = Trade(symbol="BTCUSDT", agg_id=6, ts=1000, price=105.0, qty=1.0, quote_qty=105.0, side="BUY", is_buyer_maker=False, first_id=1, last_id=1)
    engine.process_trade(t)
    
    assert 105.0 not in engine.naked_pocs
    assert 110.0 in engine.naked_pocs
