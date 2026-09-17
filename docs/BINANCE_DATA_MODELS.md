# VolHelix AI — Updated Data Models for Binance Crypto

> **Purpose:** Updated Pydantic (Python) and TypeScript models for crypto spot trading.  
> **Changes:** Remove options-specific fields, add crypto-specific fields, update symbols.

---

## 1. Python Pydantic Models

### File: `backend/models/market.py` — FULL REPLACEMENT

```python
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
    SPOT_LONG = "SPOT_LONG"
    SPOT_SHORT = "SPOT_SHORT"          # Sell existing holdings
    DCA_BUY = "DCA_BUY"               # Dollar-cost average buy
    BREAKOUT_LONG = "BREAKOUT_LONG"    # Buy on breakout
    MEAN_REVERSION = "MEAN_REVERSION"  # Buy dip / sell rip
    MOMENTUM = "MOMENTUM"             # Follow trend
    CASH = "CASH"                      # Hold USDT, no trade

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
    asset: str                     # "BTC", "ETH", "USDT"
    free: float = 0.0              # Available balance
    locked: float = 0.0            # In open orders
    total: float = 0.0             # free + locked
    value_usdt: float = 0.0        # Value in USDT

class MarketSignal(BaseModel):
    timestamp: str
    symbol: str                    # "BTCUSDT" (changed from "underlying")
    price: float
    price_change_24h: float = 0.0  # 24hr price change %
    volume_24h: float = 0.0        # 24hr trading volume in quote asset
    high_24h: float = 0.0
    low_24h: float = 0.0
    iv_current: float = 0.0        # Realized volatility (crypto doesn't have IV like options)
    iv_rank: float = 0.0           # Volatility rank (0-1)
    iv_percentile: float = 0.0     # Volatility percentile (0-1)
    regime: Regime = Regime.NORMAL
    trend: Trend = Trend.NEUTRAL
    thesis: str = ""
    confidence: float = 0.0

class RiskFlags(BaseModel):
    events: List[str] = Field(default_factory=list)
    risk_level: str = Field(default="LOW", description="'LOW', 'MEDIUM', 'HIGH'")
    size_modifier: float = Field(default=1.0)
```

### File: `backend/models/trade.py` — FULL REPLACEMENT

```python
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from backend.models.market import StrategyType, TradeStatus, OrderType, OrderSide


class TradeProposal(BaseModel):
    id: str
    symbol: str                           # "BTCUSDT" (changed from "underlying")
    strategy_type: StrategyType = StrategyType.MASTER_ORDER_FLOW
    side: str = "BUY"                     # "BUY" or "SELL"
    order_type: str = "MARKET"            # "MARKET" or "LIMIT"
    qty: float = 0.0                      # Quantity in base asset (e.g., 0.001 BTC)
    quote_qty: Optional[float] = None     # Quantity in quote asset (e.g., $100 USDT)
    limit_price: Optional[float] = None   # For LIMIT orders
    
    # Risk/Reward
    entry_price: float = 0.0
    take_profit: float = 0.0
    stop_loss: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    breakevens: List[float] = Field(default_factory=list)
    
    # Analysis
    ev: float = 0.0                       # Expected value
    dte: int = 0                          # Not relevant for spot, but kept for compatibility
    thesis: str = ""
    confidence: float = 0.0

    # Computed fields
    is_credit: bool = False               # Not relevant for spot
    net_premium: float = 0.0              # Not relevant for spot
    legs: list = Field(default_factory=list)  # Empty for spot trades


class MCPCallLog(BaseModel):
    """Log entry for every Binance API call."""
    tool: str                             # e.g., "get_price", "place_order"
    request: dict
    response: dict
    timestamp: str
    duration_ms: int


class TradeRecord(BaseModel):
    trade_id: str
    proposal: TradeProposal
    status: TradeStatus = TradeStatus.OPEN
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None
    
    # Prices
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    current_price: float = 0.0
    take_profit_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    
    # P&L
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    
    # Binance-specific
    binance_order_id: Optional[str] = None
    commission: float = 0.0
    commission_asset: str = ""
    
    # Logs
    mcp_logs: List[MCPCallLog] = Field(default_factory=list)
```

### File: `backend/models/portfolio.py` — UPDATED

```python
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
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
    
    # Positions
    open_position_count: int = 0
    balances: Dict[str, CryptoAssetBalance] = Field(default_factory=dict)
    
    # Greeks (not directly applicable to spot, but kept for regime engine)
    net_delta: float = 0.0
    net_theta: float = 0.0
    net_vega: float = 0.0
    
    # Risk
    exposure_by_symbol: Dict[str, float] = Field(default_factory=dict)
    current_regime: Regime = Regime.NORMAL
```

### File: `backend/models/debate.py` — UNCHANGED (no Alpaca dependency)

```python
# This file has no Alpaca references and stays the same
from pydantic import BaseModel, Field
from typing import Optional, List


class AgentVote(BaseModel):
    agent: str
    vote: str                   # "AGREE" or "DISAGREE"
    confidence: float
    reasoning: str
    counter_arguments: List[str] = Field(default_factory=list)

class DebateResult(BaseModel):
    proposal_id: str
    votes: List[AgentVote] = Field(default_factory=list)
    consensus_reached: bool = False
    consensus_score: float = 0.0
    winning_proposal_id: Optional[str] = None
    debate_summary: str = ""

class PostMortem(BaseModel):
    trade_id: str
    actual_pnl: float = 0.0
    expected_pnl: float = 0.0
    pnl_diff: float = 0.0
    regime_was_correct: bool = True
    strategy_score: int = 5         # 1-10
    lessons: List[str] = Field(default_factory=list)
    timestamp: str = ""
```

---

## 2. TypeScript Types

### File: `frontend/src/lib/types.ts` — UPDATED

```typescript
// ── Enums ──
export type Regime = "LOW_VOL" | "NORMAL" | "ELEVATED" | "SQUEEZE" | "CRISIS";
export type Trend = "BULLISH" | "BEARISH" | "NEUTRAL";
export type StrategyType =
  | "MASTER_ORDER_FLOW"
  | "SPOT_LONG"
  | "SPOT_SHORT"
  | "DCA_BUY"
  | "BREAKOUT_LONG"
  | "MEAN_REVERSION"
  | "MOMENTUM"
  | "CASH";
export type TradeStatus = "PENDING" | "OPEN" | "CLOSED" | "STOPPED_OUT" | "TAKE_PROFIT" | "CANCELLED";
export type OrderType = "MARKET" | "LIMIT";
export type OrderSide = "BUY" | "SELL";

// ── Watched Symbols ──
export type WatchedSymbol = "BTCUSDT" | "ETHUSDT" | "SOLUSDT" | "BNBUSDT" | "XRPUSDT";
export const WATCHED_SYMBOLS: WatchedSymbol[] = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];
export const DEFAULT_SYMBOL: WatchedSymbol = "BTCUSDT";

export const SYMBOL_DISPLAY: Record<WatchedSymbol, { name: string; icon: string }> = {
  BTCUSDT: { name: "Bitcoin", icon: "₿" },
  ETHUSDT: { name: "Ethereum", icon: "Ξ" },
  SOLUSDT: { name: "Solana", icon: "◎" },
  BNBUSDT: { name: "BNB", icon: "BNB" },
  XRPUSDT: { name: "XRP", icon: "XRP" },
};

// ── Market Signal ──
export interface MarketSignal {
  timestamp: string;
  symbol: string;          // Changed from "underlying"
  price: number;
  price_change_24h: number;
  volume_24h: number;
  high_24h: number;
  low_24h: number;
  iv_current: number;
  iv_rank: number;
  iv_percentile: number;
  regime: Regime;
  trend: Trend;
  thesis: string;
  confidence: number;
}

// ── Trade Proposal ──
export interface TradeProposal {
  id: string;
  symbol: string;
  strategy_type: StrategyType;
  side: OrderSide;
  order_type: OrderType;
  qty: number;
  quote_qty?: number;
  limit_price?: number;
  entry_price: number;
  take_profit: number;
  stop_loss: number;
  max_profit: number;
  max_loss: number;
  breakevens: number[];
  ev: number;
  thesis: string;
  confidence: number;
}

// ── Trade Record ──
export interface TradeRecord {
  trade_id: string;
  proposal: TradeProposal;
  status: TradeStatus;
  entry_time?: string;
  exit_time?: string;
  entry_price: number;
  exit_price?: number;
  current_price: number;
  take_profit_price?: number;
  stop_loss_price?: number;
  realized_pnl: number;
  unrealized_pnl: number;
  binance_order_id?: string;
  commission: number;
  commission_asset: string;
}

// ── Portfolio ──
export interface CryptoAssetBalance {
  asset: string;
  free: number;
  locked: number;
  total: number;
  value_usdt: number;
}

export interface PortfolioSnapshot {
  timestamp: string;
  equity: number;
  buying_power: number;
  daily_pnl: number;
  daily_pnl_pct: number;
  total_pnl: number;
  total_pnl_pct: number;
  open_position_count: number;
  balances: Record<string, CryptoAssetBalance>;
  net_delta: number;
  net_theta: number;
  net_vega: number;
  exposure_by_symbol: Record<string, number>;
  current_regime: Regime;
}

// ── Market Clock (always open for crypto) ──
export interface MarketClockStatus {
  is_open: boolean;            // Always true for crypto
  raw_is_open: boolean;
  simulation_active: boolean;
  simulation_override?: boolean;
  current_time_et: string;
  reason: string;
}
```

---

## 3. Key Differences from Alpaca Models

| Aspect | Old (Alpaca/Stocks/Options) | New (Binance/Crypto/Spot) |
|---|---|---|
| Symbol format | `"SPY"`, `"NVDA"` | `"BTCUSDT"`, `"ETHUSDT"` |
| Field name | `underlying` | `symbol` |
| Options legs | `legs: List[OptionLeg]` | `legs: list = []` (always empty) |
| Greeks | Per-contract | Not applicable (kept as 0 for compatibility) |
| OCC symbols | `"NVDA260906P00120000"` | Not applicable |
| Position type | Long/Short options spreads | Simple spot holdings |
| Quantity | Integer shares | Fractional (0.00001 BTC) |
| Market hours | 09:30-16:00 ET | 24/7 |
| Currency | USD | USDT (Tether) |
| Initial capital | $100,000 | 10,000 USDT |
| Strategy types | Options spreads, condors, straddles | Spot long, DCA, momentum, mean reversion |

---

> **Document Version:** 1.0  
> **Created:** September 17, 2026  
> **Purpose:** Complete data model reference for Gemini 3.8 Flash
