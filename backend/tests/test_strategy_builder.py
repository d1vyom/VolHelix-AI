import pytest
from backend.models.market import OptionLeg, StrategyType
from backend.engine.strategy_builder import (
    build_bull_put_spread,
    build_bear_call_spread,
    build_iron_condor,
    build_long_straddle,
    build_calendar_spread,
)

def test_build_bull_put_spread():
    short_put = OptionLeg(action="SELL", contract_type="PUT", strike=500.0, expiry="2026-04-15", symbol="SPY_P500", premium=5.0, delta=-0.25, gamma=0.02, theta=0.10, vega=-0.08)
    long_put = OptionLeg(action="BUY", contract_type="PUT", strike=490.0, expiry="2026-04-15", symbol="SPY_P490", premium=2.0, delta=0.15, gamma=-0.01, theta=-0.05, vega=0.05)

    prop = build_bull_put_spread("SPY", short_put, long_put, "2026-04-15", 30, "Bullish support")
    assert prop.strategy_type == StrategyType.BULL_PUT_SPREAD
    assert prop.is_credit is True
    assert prop.net_premium == 3.0   # 5.0 - 2.0
    assert prop.max_profit == 3.0
    assert prop.max_loss == 7.0     # 10.0 width - 3.0 credit
    assert prop.breakevens == [497.0]

def test_build_bear_call_spread():
    short_call = OptionLeg(action="SELL", contract_type="CALL", strike=520.0, expiry="2026-04-15", symbol="SPY_C520", premium=4.0, delta=0.25, gamma=-0.02, theta=0.12, vega=-0.08)
    long_call = OptionLeg(action="BUY", contract_type="CALL", strike=530.0, expiry="2026-04-15", symbol="SPY_C530", premium=1.5, delta=-0.15, gamma=0.01, theta=-0.06, vega=0.05)

    prop = build_bear_call_spread("SPY", short_call, long_call, "2026-04-15", 30, "Resistance at 520")
    assert prop.strategy_type == StrategyType.BEAR_CALL_SPREAD
    assert prop.is_credit is True
    assert prop.net_premium == 2.5   # 4.0 - 1.5
    assert prop.max_profit == 2.5
    assert prop.max_loss == 7.5     # 10.0 width - 2.5 credit
    assert prop.breakevens == [522.5]

def test_build_iron_condor():
    short_put = OptionLeg(action="SELL", contract_type="PUT", strike=490.0, expiry="2026-04-15", symbol="SPY_P490", premium=3.0)
    long_put = OptionLeg(action="BUY", contract_type="PUT", strike=480.0, expiry="2026-04-15", symbol="SPY_P480", premium=1.0)
    short_call = OptionLeg(action="SELL", contract_type="CALL", strike=520.0, expiry="2026-04-15", symbol="SPY_C520", premium=3.0)
    long_call = OptionLeg(action="BUY", contract_type="CALL", strike=530.0, expiry="2026-04-15", symbol="SPY_C530", premium=1.0)

    prop = build_iron_condor("SPY", short_put, long_put, short_call, long_call, "2026-04-15", 30, "Range-bound")
    assert prop.strategy_type == StrategyType.IRON_CONDOR
    assert len(prop.legs) == 4
    assert prop.is_credit is True
    assert prop.net_premium == 4.0   # (3 - 1) + (3 - 1)
    assert prop.max_loss == 6.0     # 10 width - 4 credit
    assert prop.breakevens == [486.0, 524.0]

def test_build_long_straddle():
    call_leg = OptionLeg(action="BUY", contract_type="CALL", strike=500.0, expiry="2026-04-15", symbol="SPY_C500", premium=6.0, delta=0.50, theta=-0.15, vega=0.20)
    put_leg = OptionLeg(action="BUY", contract_type="PUT", strike=500.0, expiry="2026-04-15", symbol="SPY_P500", premium=6.0, delta=-0.50, theta=-0.15, vega=0.20)

    prop = build_long_straddle("SPY", call_leg, put_leg, "2026-04-15", 30, "Volatility breakout expected")
    assert prop.strategy_type == StrategyType.LONG_STRADDLE
    assert prop.is_credit is False
    assert prop.net_premium == -12.0
    assert prop.max_loss == 12.0
    assert prop.breakevens == [488.0, 512.0]

def test_build_calendar_spread():
    short_front = OptionLeg(action="SELL", contract_type="CALL", strike=510.0, expiry="2026-04-01", symbol="SPY_C510_front", premium=2.5)
    long_back = OptionLeg(action="BUY", contract_type="CALL", strike=510.0, expiry="2026-04-20", symbol="SPY_C510_back", premium=5.0)

    prop = build_calendar_spread("SPY", short_front, long_back, "2026-04-20", 30, "Time decay capture")
    assert prop.strategy_type == StrategyType.CALENDAR_SPREAD
    assert prop.is_credit is False
    assert prop.max_loss == 2.5
