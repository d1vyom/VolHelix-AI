import numpy as np
from backend.models.market import Regime, StrategyType
try:
    from hmmlearn import hmm
    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False

# Global HMM model for regime detection
_hmm_model = None
_hmm_fitted = False

def _train_hmm_regime_model(vix_history: list[float]):
    """Train HMM model on VIX history if available."""
    global _hmm_model, _hmm_fitted
    if not HMM_AVAILABLE or len(vix_history) < 50:
        return
    
    try:
        # Prepare data: VIX returns/volatility
        vix_array = np.array(vix_history).reshape(-1, 1)
        _hmm_model = hmm.GaussianHMM(
            n_components=5,  # 5 regimes
            covariance_type="diag",
            n_iter=100,
            random_state=42
        )
        _hmm_model.fit(vix_array)
        _hmm_fitted = True
    except Exception as e:
        _hmm_fitted = False

def classify_regime(vix: float, iv_percentile: float, squeeze: bool, vix_history: list[float] = None) -> Regime:
    """
    Classify the market into 5 distinct volatility regimes.
    Uses HMM for regime detection when available, falls back to rule-based.
    Rules derived from PRD Section 6.2.
    """
    global _hmm_model, _hmm_fitted
    
    # Try HMM first if we have enough history
    if HMM_AVAILABLE and vix_history and len(vix_history) >= 50:
        if not _hmm_fitted:
            _train_hmm_regime_model(vix_history)
        
        if _hmm_fitted and _hmm_model is not None:
            try:
                # Predict current regime using HMM
                current_obs = np.array([[vix]])
                hidden_state = _hmm_model.predict(current_obs)[0]
                
                # Map HMM states to our regimes (ordered by VIX level)
                # HMM states are 0-4, we need to map them to actual VIX levels
                state_means = _hmm_model.means_.flatten()
                state_order = np.argsort(state_means)  # Low to high VIX
                
                # Map: 0=LOW_VOL, 1=NORMAL, 2=ELEVATED, 3=SQUEEZE, 4=CRISIS
                # But SQUEEZE is special (BB-based), so we handle it separately
                if squeeze:
                    return Regime.SQUEEZE
                
                regime_map = {
                    state_order[0]: Regime.LOW_VOL,
                    state_order[1]: Regime.NORMAL,
                    state_order[2]: Regime.ELEVATED,
                    state_order[3]: Regime.ELEVATED,  # Could be SQUEEZE but we handled above
                    state_order[4]: Regime.CRISIS
                }
                return regime_map.get(hidden_state, Regime.NORMAL)
            except Exception:
                pass  # Fall through to rule-based
    
    # Fallback: Rule-based classification
    if vix > 30.0 or iv_percentile > 0.80:
        return Regime.CRISIS
        
    if squeeze:
        return Regime.SQUEEZE
        
    if 20.0 <= vix <= 30.0 or 0.50 <= iv_percentile <= 0.80:
        return Regime.ELEVATED
        
    if 15.0 <= vix < 20.0 or 0.25 <= iv_percentile < 0.50:
        return Regime.NORMAL
        
    # vix < 15 and iv_percentile < 0.25
    return Regime.LOW_VOL

def get_strategy_bias(regime: Regime) -> dict:
    """
    Returns recommended strategy types, base size modifier, and ideal DTE for a regime.
    """
    bias_map = {
        Regime.LOW_VOL: {
            "strategies": [StrategyType.MASTER_ORDER_FLOW, StrategyType.CALENDAR_SPREAD, StrategyType.LONG_STRADDLE],
            "size_mod": 0.8,  # 2.0% NAV limit (0.8 * 2.5)
            "dte_range": (30, 45)
        },
        Regime.NORMAL: {
            "strategies": [StrategyType.MASTER_ORDER_FLOW, StrategyType.IRON_CONDOR, StrategyType.BULL_PUT_SPREAD, StrategyType.BEAR_CALL_SPREAD],
            "size_mod": 1.0,  # 2.5% NAV limit
            "dte_range": (30, 45)
        },
        Regime.ELEVATED: {
            "strategies": [StrategyType.MASTER_ORDER_FLOW, StrategyType.BULL_PUT_SPREAD, StrategyType.BEAR_CALL_SPREAD],
            "size_mod": 0.8,  # 2.0% NAV limit
            "dte_range": (14, 30)
        },
        Regime.SQUEEZE: {
            "strategies": [StrategyType.MASTER_ORDER_FLOW, StrategyType.LONG_STRADDLE],
            "size_mod": 0.6,  # 1.5% NAV limit
            "dte_range": (14, 30)
        },
        Regime.CRISIS: {
            "strategies": [StrategyType.PROTECTIVE_PUT, StrategyType.CASH],
            "size_mod": 0.4,  # 1.0% NAV limit
            "dte_range": (7, 21)
        }
    }
    
    return bias_map.get(regime, bias_map[Regime.NORMAL])

def detect_squeeze(vix_history: list[float], period: int = 20) -> bool:
    """Detect Bollinger Band squeeze on VIX."""
    if len(vix_history) < period:
        return False
    
    recent = vix_history[-period:]
    mean_vix = np.mean(recent)
    std_vix = np.std(recent)
    
    upper = mean_vix + 2 * std_vix
    lower = mean_vix - 2 * std_vix
    
    # BB width normalized
    bb_width = (upper - lower) / mean_vix if mean_vix > 0 else 1.0
    
    return bb_width < 0.10  # Tight compression = breakout imminent
