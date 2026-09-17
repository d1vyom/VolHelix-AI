import pytest
from backend.models.market import Regime, StrategyType
from backend.engine.regime import (
    classify_regime,
    classify_crypto_regime,
    realized_volatility,
    detect_squeeze,
    get_strategy_bias,
)

def test_regime_classification_low_vol():
    regime = classify_regime(vix_or_vol=20.0, iv_percentile=0.20, squeeze=False)
    assert regime == Regime.LOW_VOL

def test_regime_classification_normal():
    regime = classify_regime(vix_or_vol=35.0, iv_percentile=0.35, squeeze=False)
    assert regime == Regime.NORMAL

def test_regime_classification_elevated():
    regime = classify_regime(vix_or_vol=60.0, iv_percentile=0.65, squeeze=False)
    assert regime == Regime.ELEVATED

def test_regime_classification_crisis():
    # Vol > 80 or percentile > 0.80
    assert classify_regime(vix_or_vol=85.0, iv_percentile=0.70, squeeze=False) == Regime.CRISIS
    assert classify_regime(vix_or_vol=40.0, iv_percentile=0.88, squeeze=False) == Regime.CRISIS

def test_regime_classification_squeeze():
    regime = classify_regime(vix_or_vol=40.0, iv_percentile=0.40, squeeze=True)
    assert regime == Regime.SQUEEZE

def test_realized_volatility_calculation():
    # Constant prices should have 0 vol
    closes_flat = [60000.0] * 35
    assert realized_volatility(closes_flat) == 0.0

    # Moving prices should have positive annualized vol
    closes_moving = [60000.0 * (1 + 0.01 * (i % 3 - 1)) for i in range(35)]
    vol = realized_volatility(closes_moving)
    assert vol > 0.0

def test_detect_squeeze_logic():
    # Flat tight range should be detected as squeeze
    tight_prices = [50000.0 + (i % 2) * 10 for i in range(25)]
    assert detect_squeeze(tight_prices) is True

    # High variance prices should not be a squeeze
    wide_prices = [50000.0 * (1.1 ** (i % 5)) for i in range(25)]
    assert detect_squeeze(wide_prices) is False

def test_strategy_bias_returns_correct_mappings():
    bias_low = get_strategy_bias(Regime.LOW_VOL)
    assert StrategyType.SPOT_LONG in bias_low["strategies"]
    assert bias_low["size_mod"] == 1.0

    bias_normal = get_strategy_bias(Regime.NORMAL)
    assert StrategyType.MASTER_ORDER_FLOW in bias_normal["strategies"]
    assert StrategyType.SPOT_LONG in bias_normal["strategies"]
    assert bias_normal["size_mod"] == 1.0

    bias_elevated = get_strategy_bias(Regime.ELEVATED)
    assert StrategyType.MEAN_REVERSION in bias_elevated["strategies"]
    assert bias_elevated["size_mod"] == 0.75

    bias_squeeze = get_strategy_bias(Regime.SQUEEZE)
    assert StrategyType.BREAKOUT_LONG in bias_squeeze["strategies"]
    assert bias_squeeze["size_mod"] == 0.50

    bias_crisis = get_strategy_bias(Regime.CRISIS)
    assert StrategyType.CASH in bias_crisis["strategies"]
    assert StrategyType.SPOT_SHORT in bias_crisis["strategies"]
    assert bias_crisis["size_mod"] == 0.25
