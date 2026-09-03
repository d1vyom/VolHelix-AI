import pytest
from backend.engine.iv_calculator import calculate_iv_rank, calculate_iv_percentile

def test_iv_rank_boundaries():
    # At low
    assert calculate_iv_rank(current_iv=0.12, iv_high_52w=0.30, iv_low_52w=0.12) == 0.0
    # At high
    assert calculate_iv_rank(current_iv=0.30, iv_high_52w=0.30, iv_low_52w=0.12) == 1.0
    # Midpoint
    assert calculate_iv_rank(current_iv=0.21, iv_high_52w=0.30, iv_low_52w=0.12) == 0.5

def test_iv_rank_clamped():
    # Below low
    assert calculate_iv_rank(current_iv=0.08, iv_high_52w=0.30, iv_low_52w=0.12) == 0.0
    # Above high
    assert calculate_iv_rank(current_iv=0.45, iv_high_52w=0.30, iv_low_52w=0.12) == 1.0

def test_iv_rank_degenerate_range():
    # high <= low
    assert calculate_iv_rank(current_iv=0.20, iv_high_52w=0.15, iv_low_52w=0.15) == 0.5

def test_iv_percentile_calculation():
    history = [0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.22, 0.24, 0.26, 0.28]
    # Current IV 0.19 has 5 values below (0.10, 0.12, 0.14, 0.16, 0.18) -> 5/10 = 0.50
    assert calculate_iv_percentile(0.19, history) == 0.50

    # Current IV 0.30 has all 10 below -> 1.0
    assert calculate_iv_percentile(0.30, history) == 1.0

    # Current IV 0.05 has 0 below -> 0.0
    assert calculate_iv_percentile(0.05, history) == 0.0

def test_iv_percentile_empty_history():
    assert calculate_iv_percentile(0.20, []) == 0.50
