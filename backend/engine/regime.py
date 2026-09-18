import numpy as np
from typing import List, Optional
from backend.models.market import Regime, StrategyType

try:
    from hmmlearn import hmm
    HMM_AVAILABLE = True
except ImportError:
    hmm = None  # type: ignore[assignment]
    HMM_AVAILABLE = False

# Global HMM model for regime detection
_hmm_model = None
_hmm_fitted = False


def realized_volatility(closes: List[float], window: int = 30) -> float:
    """
    Calculate annualized realized volatility from closing prices.
    Uses 365 days for continuous 24/7 crypto markets.
    """
    if len(closes) < window + 1:
        return 0.0
    log_returns = np.diff(np.log(closes[-window - 1:]))
    daily_vol = np.std(log_returns)
    annualized = daily_vol * np.sqrt(365)
    return float(annualized * 100.0)


def detect_squeeze(prices: List[float], period: int = 20) -> bool:
    """Detect Bollinger Band compression on price or volatility."""
    if len(prices) < period:
        return False
    
    recent = prices[-period:]
    mean_val = np.mean(recent)
    std_val = np.std(recent)
    
    if mean_val <= 0:
        return False

    upper = mean_val + 2 * std_val
    lower = mean_val - 2 * std_val
    bb_width = (upper - lower) / mean_val
    
    return bool(bb_width < 0.06)  # Tight compression indicates imminent breakout


def _train_hmm_regime_model(vol_history: List[float]):
    """Train HMM model on volatility history if available."""
    global _hmm_model, _hmm_fitted
    if hmm is None or not HMM_AVAILABLE or len(vol_history) < 50:
        return
    
    try:
        vol_array = np.array(vol_history).reshape(-1, 1)
        _hmm_model = hmm.GaussianHMM(
            n_components=5,
            covariance_type="diag",
            n_iter=100,
            random_state=42
        )
        _hmm_model.fit(vol_array)
        _hmm_fitted = True
    except Exception:
        _hmm_fitted = False


def classify_crypto_regime(
    btc_realized_vol_30d: float,
    vol_percentile: float = 0.5,
    squeeze_detected: bool = False
) -> Regime:
    """
    Deterministic regime classification for crypto. Zero LLM.
    """
    if btc_realized_vol_30d > 80.0 or vol_percentile > 0.80:
        return Regime.CRISIS
    elif squeeze_detected:
        return Regime.SQUEEZE
    elif btc_realized_vol_30d > 50.0 or vol_percentile > 0.50:
        return Regime.ELEVATED
    elif btc_realized_vol_30d < 25.0 and vol_percentile < 0.25:
        return Regime.LOW_VOL
    else:
        return Regime.NORMAL


def classify_regime(
    vix_or_vol: float,
    iv_percentile: float = 0.5,
    squeeze: bool = False,
    vix_history: Optional[List[float]] = None
) -> Regime:
    """
    Main regime classifier.
    Supports crypto realized vol (standard) or legacy VIX inputs.
    """
    global _hmm_model, _hmm_fitted
    
    # Try HMM first if sufficient history is available
    if HMM_AVAILABLE and vix_history and len(vix_history) >= 50:
        if not _hmm_fitted:
            _train_hmm_regime_model(vix_history)
        
        if _hmm_fitted and _hmm_model is not None:
            try:
                current_obs = np.array([[vix_or_vol]])
                hidden_state = _hmm_model.predict(current_obs)[0]
                state_means = _hmm_model.means_.flatten()
                state_order = np.argsort(state_means)
                
                if squeeze:
                    return Regime.SQUEEZE
                
                regime_map = {
                    state_order[0]: Regime.LOW_VOL,
                    state_order[1]: Regime.NORMAL,
                    state_order[2]: Regime.ELEVATED,
                    state_order[3]: Regime.ELEVATED,
                    state_order[4]: Regime.CRISIS
                }
                return regime_map.get(hidden_state, Regime.NORMAL)
            except Exception:
                pass

    # Fallback to deterministic crypto rules
    return classify_crypto_regime(
        btc_realized_vol_30d=vix_or_vol,
        vol_percentile=iv_percentile,
        squeeze_detected=squeeze
    )


def get_strategy_bias(regime: Regime) -> dict:
    """
    Returns the recommended strategy and size modifier for a volatility regime.

    VolHelix trades a single strategy (the Master Order Flow confluence setup), so
    every regime recommends it and only the position-size modifier changes. CRISIS
    is the sole exception: it stands aside in CASH at 0.25x size.
    """
    bias_map = {
        Regime.LOW_VOL: {
            "strategies": [StrategyType.MASTER_ORDER_FLOW],
            "size_mod": 1.0,
            "dte_range": (0, 0),
        },
        Regime.NORMAL: {
            "strategies": [StrategyType.MASTER_ORDER_FLOW],
            "size_mod": 1.0,
            "dte_range": (0, 0),
        },
        Regime.ELEVATED: {
            "strategies": [StrategyType.MASTER_ORDER_FLOW],
            "size_mod": 0.75,
            "dte_range": (0, 0),
        },
        Regime.SQUEEZE: {
            "strategies": [StrategyType.MASTER_ORDER_FLOW],
            "size_mod": 0.50,
            "dte_range": (0, 0),
        },
        Regime.CRISIS: {
            "strategies": [StrategyType.CASH],
            "size_mod": 0.25,
            "dte_range": (0, 0),
        },
    }
    return bias_map.get(regime, bias_map[Regime.NORMAL])
