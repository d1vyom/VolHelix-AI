import pytest
from backend.engine.footprint import FootprintEngine
from backend.marketdata.models import Trade
from backend.config import settings

def test_footprint_bar_generation():
    settings.FLOW_TICK_GROUP_MULTIPLIER = 1.0
    settings.FLOW_IMBALANCE_MIN_VOLUME = 5.0
    settings.FLOW_IMBALANCE_RATIO = 3.0
    settings.FLOW_STACKED_IMBALANCE_MIN = 3
    settings.FLOW_VALUE_AREA_PCT = 0.7
    
    engine = FootprintEngine("BTCUSDT", "1m", 1.0)
    
    trades = [
        Trade(symbol="BTCUSDT", agg_id=1, ts=1000, price=100.0, qty=10.0, quote_qty=1000.0, side="BUY", is_buyer_maker=False, first_id=1, last_id=1),
        Trade(symbol="BTCUSDT", agg_id=2, ts=2000, price=100.0, qty=2.0, quote_qty=200.0, side="SELL", is_buyer_maker=True, first_id=2, last_id=2),
        Trade(symbol="BTCUSDT", agg_id=3, ts=3000, price=101.0, qty=10.0, quote_qty=1010.0, side="BUY", is_buyer_maker=False, first_id=3, last_id=3),
        Trade(symbol="BTCUSDT", agg_id=4, ts=4000, price=101.0, qty=2.0, quote_qty=202.0, side="SELL", is_buyer_maker=True, first_id=4, last_id=4),
        Trade(symbol="BTCUSDT", agg_id=5, ts=5000, price=102.0, qty=10.0, quote_qty=1020.0, side="BUY", is_buyer_maker=False, first_id=5, last_id=5),
        Trade(symbol="BTCUSDT", agg_id=6, ts=6000, price=102.0, qty=2.0, quote_qty=204.0, side="SELL", is_buyer_maker=True, first_id=6, last_id=6),
        Trade(symbol="BTCUSDT", agg_id=7, ts=7000, price=103.0, qty=10.0, quote_qty=1030.0, side="BUY", is_buyer_maker=False, first_id=7, last_id=7),
    ]
    
    for t in trades:
        engine.process_trade(t)
        
    # Trigger close
    closed, forming = engine.process_trade(Trade(symbol="BTCUSDT", agg_id=8, ts=60000, price=103.0, qty=1.0, quote_qty=103.0, side="BUY", is_buyer_maker=False, first_id=8, last_id=8))
    
    assert closed is not None
    assert closed.volume == 46.0 # 10+2+10+2+10+2+10
    assert closed.delta == 34.0 # 40 buys, 6 sells -> 34
    
    c100 = next(c for c in closed.cells if c.price == 100)
    c101 = next(c for c in closed.cells if c.price == 101)
    c102 = next(c for c in closed.cells if c.price == 102)
    c103 = next(c for c in closed.cells if c.price == 103)
    
    assert c101.buy_imbalance is True # buy 10 >= 3 * 2 (c100 sell)
    assert c102.buy_imbalance is True # buy 10 >= 3 * 2 (c101 sell)
    assert c103.buy_imbalance is True # buy 10 >= 3 * 2 (c102 sell)
    
    assert len(closed.stacked_buy_imbalance_zones) == 1
    assert closed.stacked_buy_imbalance_zones[0] == [101.0, 103.0]
    
    # POC should be tied for max total volume, picking closest to VWAP
    # VWAP = (100*12 + 101*12 + 102*12 + 103*10) / 46 = 4666 / 46 = 101.43
    # POC ties: 100, 101, 102. Closest to 101.43 is 101.
    assert closed.poc_price == 101.0
