from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator


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
    SPOT_LONG = "SPOT_LONG"
    SPOT_SHORT = "SPOT_SHORT"          # Sell existing holdings
    DCA_BUY = "DCA_BUY"               # Dollar-cost average buy
    BREAKOUT_LONG = "BREAKOUT_LONG"    # Buy on breakout
    MEAN_REVERSION = "MEAN_REVERSION"  # Buy dip / sell rip
    MOMENTUM = "MOMENTUM"             # Follow trend
    CASH = "CASH"                      # Hold USDT, no trade
    
    # Backward compatibility and strategy aliases
    VOL_BREAKOUT = "BREAKOUT_LONG"
    MOMENTUM_EXPANSION = "MOMENTUM"
    BULL_PUT_SPREAD = "SPOT_LONG"
    BEAR_CALL_SPREAD = "SPOT_SHORT"
    IRON_CONDOR = "MEAN_REVERSION"
    LONG_STRADDLE = "BREAKOUT_LONG"
    CALENDAR_SPREAD = "DCA_BUY"
    PROTECTIVE_PUT = "CASH"


class TradeStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    STOPPED_OUT = "STOPPED_OUT"
    TAKE_PROFIT = "TAKE_PROFIT"
    CANCELLED = "CANCELLED"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class CryptoAssetBalance(BaseModel):
    """Balance for a single crypto asset."""
    asset: str                         # e.g., "BTC", "ETH", "USDT"
    free: float = 0.0                  # Available balance
    locked: float = 0.0                # In open orders
    total: float = 0.0                 # free + locked
    value_usdt: float = 0.0            # Valuation in USDT


# Legacy OptionLeg retained for zero-breakage progressive migration
class OptionLeg(BaseModel):
    action: str = Field(default="BUY", description="'BUY' or 'SELL'")
    contract_type: str = Field(default="CALL", description="'CALL' or 'PUT'")
    strike: float = 0.0
    expiry: str = ""
    symbol: str = Field(default="", description="Identifier or OCC Symbol")
    premium: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    oi: int = 0
    bid: float = 0.0
    ask: float = 0.0


class MarketSignal(BaseModel):
    timestamp: str = ""
    symbol: str = ""                   # e.g., "BTCUSDT"
    underlying: Optional[str] = None   # Compatibility alias with symbol
    price: float = 0.0
    price_change_24h: float = 0.0      # 24hr price change %
    volume_24h: float = 0.0            # 24hr trading volume in quote asset
    high_24h: float = 0.0
    low_24h: float = 0.0
    iv_current: float = 0.0            # Realized volatility
    iv_rank: float = 0.0               # Volatility rank (0-1)
    iv_percentile: float = 0.0         # Volatility percentile (0-1)
    regime: Regime = Regime.NORMAL
    trend: Trend = Trend.NEUTRAL
    thesis: str = ""
    confidence: float = 0.0

    @model_validator(mode="before")
    @classmethod
    def sync_symbol_and_underlying(cls, data: any):
        if isinstance(data, dict):
            if "symbol" in data and not data.get("underlying"):
                data["underlying"] = data["symbol"]
            elif "underlying" in data and not data.get("symbol"):
                data["symbol"] = data["underlying"]
        return data


class RiskFlags(BaseModel):
    events: List[str] = Field(default_factory=list)
    risk_level: str = Field(default="LOW", description="'LOW', 'MEDIUM', 'HIGH'")
    size_modifier: float = Field(default=1.0)
