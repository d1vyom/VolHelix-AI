from typing import List, Optional
from pydantic import BaseModel, Field
from backend.models.market import OptionLeg, StrategyType, TradeStatus

class TradeProposal(BaseModel):
    id: str
    underlying: str
    strategy_type: StrategyType
    legs: List[OptionLeg] = Field(default_factory=list)
    is_credit: bool = True
    net_premium: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    breakevens: List[float] = Field(default_factory=list)
    net_delta: float = 0.0
    net_theta: float = 0.0
    net_vega: float = 0.0
    dte: int = 21
    ev: float = Field(default=0.0, description="Expected Value")
    thesis: str = ""
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    order_type: str = "MARKET"
    limit_price: Optional[float] = None
    side: str = "BUY"
    qty: float = 1.0

    def calculate_max_loss(self) -> float:
        return self.max_loss

class MCPCallLog(BaseModel):
    tool: str
    request: dict
    response: dict
    timestamp: str
    duration_ms: int

class TradeRecord(BaseModel):
    trade_id: str
    proposal: TradeProposal
    status: TradeStatus
    entry_time: str
    exit_time: Optional[str] = None
    realized_pnl: float = 0.0
    take_profit_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    exit_price: Optional[float] = None
    current_price: Optional[float] = None
    mcp_logs: List[MCPCallLog] = Field(default_factory=list)
