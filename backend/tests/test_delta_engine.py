import pytest
import time
from backend.engine.delta_engine import DeltaEngine
from backend.marketdata.models import Trade

def test_delta_engine_cvd_divergence():
    engine = DeltaEngine("BTCUSDT")
    now = (int(time.time() * 1000) // 60000) * 60000 - 60000
    
    # Helper to simulate 1-minute intervals and a trade
    def add_point(price, qty, side, min_offset):
        ts = now + min_offset * 60000
        t = Trade(symbol="BTCUSDT", agg_id=1, ts=ts, price=price, qty=qty, quote_qty=price*qty, side=side, is_buyer_maker=(side=="SELL"), first_id=1, last_id=1)
        engine.process_trade(t)
        return engine.cvd_history[-1] if engine.cvd_history else None
        
    for i in range(25):
        add_point(100.0, 10.0, "BUY", i)
        
    assert engine.session_cvd == 250.0
    
    p = add_point(110.0, 1.0, "SELL", 25)
    # price 110 (higher high), cvd 199 (lower high than 200) -> BEARISH
    assert p is not None
    assert p.divergence == "BEARISH"
    
def test_delta_engine_flat_divergence():
    engine = DeltaEngine("BTCUSDT")
    now = (int(time.time() * 1000) // 60000) * 60000 - 60000
    for i in range(25):
        t = Trade(symbol="BTCUSDT", agg_id=i, ts=now + i * 60000, price=100.0, qty=10.0, quote_qty=1000.0, side="BUY", is_buyer_maker=False, first_id=1, last_id=1)
        engine.process_trade(t)
        
    assert engine.cvd_history[-1].divergence is None
