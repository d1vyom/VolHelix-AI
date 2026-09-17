from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from backend.models.market import Regime, CryptoAssetBalance


class PortfolioSnapshot(BaseModel):
    timestamp: str = ""
    
    # Account totals (in USDT)
    equity: float = 10000.0               # Total portfolio value in USDT
    buying_power: float = 10000.0         # Available USDT for trading
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    
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
