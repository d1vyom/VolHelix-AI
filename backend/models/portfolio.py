from typing import List, Dict, Any
from pydantic import BaseModel, Field
from backend.models.market import Regime

class PortfolioSnapshot(BaseModel):
    timestamp: str
    equity: float
    buying_power: float
    daily_pnl: float
    total_pnl: float
    open_positions: int
    net_delta: float
    net_theta: float
    net_vega: float
    current_regime: Regime
    exposures: Dict[str, float] = Field(default_factory=dict)
