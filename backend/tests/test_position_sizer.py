import pytest
from backend.models.market import Regime, RiskFlags
from backend.engine.position_sizer import kelly_criterion, calculate_position_size

def test_kelly_criterion_zero_win_rate():
    assert kelly_criterion(win_rate=0.0, avg_win=100.0, avg_loss=100.0) == 0.0

def test_kelly_criterion_zero_payoffs():
    assert kelly_criterion(win_rate=0.60, avg_win=0.0, avg_loss=100.0) == 0.0
    assert kelly_criterion(win_rate=0.60, avg_win=100.0, avg_loss=0.0) == 0.0

def test_kelly_criterion_standard_edge():
    # 60% win rate, 1:1 payoff -> f* = 0.60 - 0.40/1.0 = 0.20 -> half kelly = 0.10
    k = kelly_criterion(win_rate=0.60, avg_win=100.0, avg_loss=100.0)
    assert pytest.approx(k, 0.01) == 0.10

def test_calculate_position_size_normal_regime(clean_risk_flags):
    # nav = $100,000, max_position_pct = 0.025 ($2,500)
    # Kelly fraction = 0.05
    dollar_size = calculate_position_size(
        kelly_fraction=0.05,
        nav=100000.0,
        regime=Regime.NORMAL,
        risk_flags=clean_risk_flags
    )
    # Constrained by max 2.5% = $2,500
    assert dollar_size == 2500.0

def test_calculate_position_size_elevated_regime_reduced(clean_risk_flags):
    # In ELEVATED regime, size_mod = 0.8 -> 2.5% * 0.8 = 2.0% ($2,000)
    dollar_size = calculate_position_size(
        kelly_fraction=0.05,
        nav=100000.0,
        regime=Regime.ELEVATED,
        risk_flags=clean_risk_flags
    )
    assert pytest.approx(dollar_size, 0.01) == 2000.0

def test_calculate_position_size_event_risk_modifier():
    # High event risk: size_modifier = 0.5
    flags = RiskFlags(events=["FOMC"], risk_level="HIGH", size_modifier=0.5)
    dollar_size = calculate_position_size(
        kelly_fraction=0.05,
        nav=100000.0,
        regime=Regime.NORMAL,
        risk_flags=flags
    )
    # 2.5% * 1.0 * 0.5 = 1.25% ($1,250)
    assert dollar_size == 1250.0
