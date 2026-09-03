from typing import List, Optional
from pydantic import BaseModel, Field
from backend.models.market import OptionLeg, StrategyType, TradeStatus

class TradeProposal(BaseModel):
    id: str
    underlying: str
    strategy_type: StrategyType
    legs: List[OptionLeg]
    is_credit: bool
    net_premium: float
    max_profit: float
    max_loss: float
    breakevens: List[float]
    net_delta: float = 0.0
    net_theta: float = 0.0
    net_vega: float = 0.0
    dte: int
    ev: float = Field(description="Expected Value")
    thesis: str
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None

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
    mcp_logs: List[MCPCallLog] = Field(default_factory=list)
