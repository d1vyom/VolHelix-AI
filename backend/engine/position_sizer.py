from backend.config import settings
from backend.models.market import Regime, RiskFlags
from backend.engine.regime import get_strategy_bias

def kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Calculate the Kelly fraction.
    f* = (p - (1-p)) / (avg_win/avg_loss) if assuming identical payoffs.
    Generally: f* = p/a - q/b (where a = loss ratio, b = win ratio).
    Standard simplified: f* = W - ((1-W) / (W/L ratio))
    """
    if avg_loss == 0 or avg_win == 0:
        return 0.0
        
    win_loss_ratio = avg_win / abs(avg_loss)
    kelly_fraction = win_rate - ((1.0 - win_rate) / win_loss_ratio)
    
    # Half-Kelly for safety
    return max(0.0, kelly_fraction * 0.5)

def calculate_position_size(kelly_fraction: float, nav: float, regime: Regime, risk_flags: RiskFlags) -> float:
    """
    Calculate dollar amount to risk for a trade based on Kelly, Regime, and Risk Events.
    """
    # 1. Base cap from config
    max_risk_pct = settings.MAX_POSITION_PCT
    
    # 2. Apply regime modifier
    bias = get_strategy_bias(regime)
    regime_mod = bias.get("size_mod", 1.0)
    
    # 3. Apply event risk modifier
    event_mod = risk_flags.size_modifier
    
    # 4. Final constrained fraction
    final_fraction = min(kelly_fraction, max_risk_pct * regime_mod * event_mod)
    
    return nav * final_fraction
