import pytest
from backend.models.market import Regime, StrategyType
from backend.engine.regime import classify_regime, get_strategy_bias

def test_regime_classification_low_vol():
    regime = classify_regime(vix=12.5, iv_percentile=0.15, squeeze=False)
    assert regime == Regime.LOW_VOL

def test_regime_classification_normal():
    regime = classify_regime(vix=17.0, iv_percentile=0.35, squeeze=False)
    assert regime == Regime.NORMAL

def test_regime_classification_elevated():
    regime = classify_regime(vix=24.0, iv_percentile=0.65, squeeze=False)
    assert regime == Regime.ELEVATED

def test_regime_classification_crisis():
    # VIX > 30 or iv_percentile > 0.80
    assert classify_regime(vix=35.0, iv_percentile=0.70, squeeze=False) == Regime.CRISIS
    assert classify_regime(vix=18.0, iv_percentile=0.88, squeeze=False) == Regime.CRISIS

def test_regime_classification_squeeze():
    regime = classify_regime(vix=18.0, iv_percentile=0.40, squeeze=True)
    assert regime == Regime.SQUEEZE

def test_strategy_bias_returns_correct_mappings():
    bias_low = get_strategy_bias(Regime.LOW_VOL)
    assert StrategyType.CALENDAR_SPREAD in bias_low["strategies"]
    assert bias_low["size_mod"] == 0.8

    bias_normal = get_strategy_bias(Regime.NORMAL)
    assert StrategyType.IRON_CONDOR in bias_normal["strategies"]
    assert StrategyType.BULL_PUT_SPREAD in bias_normal["strategies"]
    assert bias_normal["size_mod"] == 1.0

    bias_elevated = get_strategy_bias(Regime.ELEVATED)
    assert StrategyType.BULL_PUT_SPREAD in bias_elevated["strategies"]
    assert bias_elevated["dte_range"] == (14, 30)

    bias_squeeze = get_strategy_bias(Regime.SQUEEZE)
    assert StrategyType.LONG_STRADDLE in bias_squeeze["strategies"]

    bias_crisis = get_strategy_bias(Regime.CRISIS)
    assert StrategyType.CASH in bias_crisis["strategies"] or StrategyType.PROTECTIVE_PUT in bias_crisis["strategies"]
