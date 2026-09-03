from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class AgentVote(BaseModel):
    agent_name: str
    vote: str = Field(description="'AGREE' or 'DISAGREE'")
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    counter_arguments: List[str] = Field(default_factory=list)

class DebateResult(BaseModel):
    proposal_id: str
    votes: List[AgentVote] = Field(default_factory=list)
    consensus_reached: bool
    consensus_score: float
    winning_proposal_id: Optional[str] = None
    summary: str

class PostMortem(BaseModel):
    trade_id: str
    actual_pnl: float
    expected_pnl: float
    pnl_diff: float
    regime_was_correct: bool
    strategy_score: int = Field(ge=1, le=10)
    lessons: List[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
