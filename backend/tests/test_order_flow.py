import pytest
from backend.models.market import OptionLeg, StrategyType
from backend.engine.order_flow import (
    detect_order_blocks,
    detect_fair_value_gaps,
    compute_liquidity_heatmap,
    analyze_order_flow
)
from backend.engine.gamma_profile import calculate_gamma_profile
from backend.engine.strategy_builder import build_master_order_flow_strategy

def test_detect_order_blocks_bullish_and_bearish():
    # Synthetic bars simulating a swing low, bearish setup candle, then sharp 2-candle upward displacement
    bars = [
        {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5, "volume": 1000},
        {"open": 100.5, "high": 101.2, "low": 100.0, "close": 100.8, "volume": 1100},
        # Bearish candle before breakout (Order Block)
        {"open": 100.8, "high": 101.0, "low": 98.0, "close": 98.5, "volume": 1500},
        # Impulsive breakout candle 1
        {"open": 98.5, "high": 103.0, "low": 98.5, "close": 102.5, "volume": 3500},
        # Impulsive breakout candle 2 (breaking high)
        {"open": 102.5, "high": 106.0, "low": 102.0, "close": 105.5, "volume": 4000},
        {"open": 105.5, "high": 107.0, "low": 105.0, "close": 106.5, "volume": 2000},
    ]
    obs = detect_order_blocks(bars, atr_period=5)
    assert len(obs) > 0
    bullish_obs = [ob for ob in obs if ob.block_type == "BULLISH"]
    assert len(bullish_obs) > 0
    assert bullish_obs[0].low <= 98.5
    assert bullish_obs[0].high >= 100.8

def test_detect_fair_value_gaps():
    # 3-candle sequence creating a Bullish FVG:
    # Candle 1: High = 100.0
    # Candle 2: Big expansion
    # Candle 3: Low = 102.0 (Leaves gap between 100.0 and 102.0)
    bars = [
        {"open": 99.0, "high": 100.0, "low": 98.0, "close": 99.5, "volume": 1000},
        {"open": 99.5, "high": 104.0, "low": 99.5, "close": 103.5, "volume": 3000},
        {"open": 103.5, "high": 105.0, "low": 102.0, "close": 104.5, "volume": 1500},
    ]
    fvgs = detect_fair_value_gaps(bars)
    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg.gap_type == "BULLISH"
    assert fvg.bottom == 100.0
    assert fvg.top == 102.0
    assert fvg.size == 2.0

def test_gamma_profile_calculation():
    spot_price = 500.0
    legs = [
        {"strike": 490.0, "type": "PUT", "gamma": 0.03, "open_interest": 5000},
        {"strike": 495.0, "type": "PUT", "gamma": 0.04, "open_interest": 8000},
        {"strike": 500.0, "type": "CALL", "gamma": 0.05, "open_interest": 6000},
        {"strike": 505.0, "type": "CALL", "gamma": 0.04, "open_interest": 10000},
        {"strike": 510.0, "type": "CALL", "gamma": 0.02, "open_interest": 4000},
    ]
    prof = calculate_gamma_profile(legs, spot_price)
    assert prof.spot_price == spot_price
    assert prof.call_wall == 505.0
    assert prof.put_wall in [490.0, 495.0]
    assert prof.regime in ["POSITIVE_GAMMA", "NEGATIVE_GAMMA"]
    assert len(prof.levels) == 5

def test_analyze_order_flow_pipeline():
    bars = [
        {"open": 500.0, "high": 502.0, "low": 498.0, "close": 499.0, "volume": 5000},
        {"open": 499.0, "high": 505.0, "low": 499.0, "close": 504.0, "volume": 8000},
        {"open": 504.0, "high": 508.0, "low": 503.0, "close": 507.0, "volume": 7000},
        {"open": 507.0, "high": 510.0, "low": 506.0, "close": 509.0, "volume": 6000},
    ]
    result = analyze_order_flow("SPY", bars)
    assert result.symbol == "SPY"
    assert result.current_price == 509.0
    assert result.trend_bias in ["BULLISH", "BEARISH", "NEUTRAL"]

def test_build_master_order_flow_strategy():
    short_put = OptionLeg(
        action="SELL",
        contract_type="PUT",
        strike=560.0,
        expiry="2026-10-16",
        symbol="SPY261016P00560000",
        premium=2.50,
        delta=-0.18
    )
    long_put = OptionLeg(
        action="BUY",
        contract_type="PUT",
        strike=555.0,
        expiry="2026-10-16",
        symbol="SPY261016P00555000",
        premium=1.20,
        delta=-0.10
    )
    net_cred = short_put.premium - long_put.premium
    max_loss = (short_put.strike - long_put.strike) - net_cred
    proposal = build_master_order_flow_strategy(
        underlying="SPY",
        legs=[short_put, long_put],
        is_credit=True,
        net_premium=net_cred,
        max_profit=net_cred,
        max_loss=max_loss,
        breakevens=[short_put.strike - net_cred],
        dte=30,
        thesis="Anchored below Bullish Order Block and Gamma Put Wall",
        take_profit=round(net_cred * 0.50, 2),
        stop_loss=round(net_cred * 1.50, 2)
    )
    assert proposal.strategy_type == StrategyType.MASTER_ORDER_FLOW
    assert proposal.is_credit is True
    assert proposal.net_premium == 1.30
    assert proposal.max_profit == 1.30
    assert proposal.max_loss == 3.70
    assert proposal.take_profit == 0.65
    assert proposal.stop_loss == 1.95
