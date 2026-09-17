from pydantic import BaseModel, Field, model_validator
from typing import Optional, List

from backend.models.market import StrategyType, TradeStatus, OrderType, OrderSide, OptionLeg


class TradeProposal(BaseModel):
    id: str
    symbol: str = ""                       # e.g., "BTCUSDT"
    underlying: Optional[str] = None       # Compatibility alias with symbol
    strategy_type: StrategyType = StrategyType.MASTER_ORDER_FLOW
    side: str = "BUY"                     # "BUY" or "SELL"
    order_type: str = "MARKET"            # "MARKET" or "LIMIT"
    qty: float = 0.0                      # Quantity in base asset (e.g., 0.001 BTC)
    quote_qty: Optional[float] = None     # Quantity in quote asset (e.g., 100 USDT)
    limit_price: Optional[float] = None   # For LIMIT orders
    
    # Risk/Reward
    entry_price: float = 0.0
    take_profit: Optional[float] = 0.0
    stop_loss: Optional[float] = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    breakevens: List[float] = Field(default_factory=list)
    
    # Analysis & Greeks (kept for regime engine / compatibility)
    ev: float = 0.0
    dte: int = 0
    net_delta: float = 0.0
    net_theta: float = 0.0
    net_vega: float = 0.0
    thesis: str = ""
    confidence: float = 0.0

    # Computed fields / compatibility
    is_credit: bool = False
    net_premium: float = 0.0
    legs: List[OptionLeg] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def sync_symbol_and_underlying(cls, data: any):
        if isinstance(data, dict):
            if "symbol" in data and not data.get("underlying"):
                data["underlying"] = data["symbol"]
            elif "underlying" in data and not data.get("symbol"):
                data["symbol"] = data["underlying"]
        return data

    def calculate_max_loss(self) -> float:
        if self.max_loss > 0:
            return self.max_loss
        return (self.entry_price or 0.0) * (self.qty or 0.0)


class MCPCallLog(BaseModel):
    """Log entry for every Binance API call."""
    tool: str
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
    current_price: Optional[float] = 0.0
    take_profit_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    
    # P&L
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    
    # Binance-specific execution metadata
    binance_order_id: Optional[str] = None
    commission: float = 0.0
    commission_asset: str = ""
    
    # Logs
    mcp_logs: List[MCPCallLog] = Field(default_factory=list)
