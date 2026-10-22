from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, model_validator
from backend.models.market import Regime, CryptoAssetBalance


class PortfolioSnapshot(BaseModel):
    timestamp: str = ""
    
    # Account totals (in USDT)
    equity: float = 10000.0               # Total portfolio value in USDT
    buying_power: float = 10000.0         # Available USDT for trading
    daily_risk_available: bool = True
    account_available: bool = False
    daily_pnl: float | None = None
    daily_pnl_pct: float | None = None
    total_pnl: float | None = None
    total_pnl_pct: float | None = None

    @model_validator(mode='after')
    def require_daily_observation(self):
        """Unknown daily PnL never authorizes the deterministic risk gate."""
        if self.daily_pnl is None:
            self.daily_risk_available=False
        return self
    
    # Positions & Balances
    open_positions: int = 0
    open_position_count: int = 0
    balances: Dict[str, CryptoAssetBalance] = Field(default_factory=dict)
    
    # Greeks (kept for analytics compatibility)
    net_delta: float = 0.0
    net_theta: float = 0.0
    net_vega: float = 0.0
    
    # Risk
    exposures: Dict[str, float] = Field(default_factory=dict)
    exposure_by_symbol: Dict[str, float] = Field(default_factory=dict)
    current_regime: Regime = Regime.NORMAL
