from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

class Regime(str, Enum):
    LOW_VOL = "LOW_VOL"
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    SQUEEZE = "SQUEEZE"
    CRISIS = "CRISIS"

class Trend(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

class StrategyType(str, Enum):
    MASTER_ORDER_FLOW = "MASTER_ORDER_FLOW"
    BULL_PUT_SPREAD = "BULL_PUT_SPREAD"
    BEAR_CALL_SPREAD = "BEAR_CALL_SPREAD"
    IRON_CONDOR = "IRON_CONDOR"
    LONG_STRADDLE = "LONG_STRADDLE"
    CALENDAR_SPREAD = "CALENDAR_SPREAD"
    PROTECTIVE_PUT = "PROTECTIVE_PUT"
    CASH = "CASH"

class TradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    STOPPED_OUT = "STOPPED_OUT"
    TAKE_PROFIT = "TAKE_PROFIT"

class OptionLeg(BaseModel):
    action: str = Field(description="'BUY' or 'SELL'")
    contract_type: str = Field(description="'CALL' or 'PUT'")
    strike: float
    expiry: str
    symbol: str = Field(description="OCC Symbol")
    premium: float
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    oi: int = 0
    bid: float = 0.0
    ask: float = 0.0

class MarketSignal(BaseModel):
    timestamp: str
    underlying: str
    price: float
    iv_current: float
    iv_rank: float
    iv_percentile: float
    regime: Regime
    trend: Trend
    thesis: str
    confidence: float

class RiskFlags(BaseModel):
    events: List[str] = Field(default_factory=list)
    risk_level: str = Field(default="LOW", description="'LOW', 'MEDIUM', 'HIGH'")
    size_modifier: float = Field(default=1.0)
