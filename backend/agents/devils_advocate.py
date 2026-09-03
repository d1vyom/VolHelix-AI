from typing import List
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from backend.config import settings
from backend.models.market import MarketSignal, RiskFlags
from backend.models.trade import TradeProposal
from backend.models.debate import AgentVote
from backend.utils.logger import get_logger

logger = get_logger("devils_advocate")

class AdvocateResponse(BaseModel):
    vote: str = Field(description="'AGREE' or 'DISAGREE'")
    confidence: float = Field(description="0.0 to 1.0")
    reasoning: str
    counter_arguments: List[str]

class DevilsAdvocateAgent:
    """Challenges proposed trades to prevent hallucinated or risky decisions."""
    
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL, 
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.7 # Higher temp for more creative counter-arguments
        )
        self.structured_llm = self.llm.with_structured_output(AdvocateResponse)
        
    def evaluate(self, proposals: List[TradeProposal], signal: MarketSignal, risk: RiskFlags) -> List[AgentVote]:
        votes = []
        for prop in proposals:
            logger.info(f"Devil's Advocate evaluating proposal {prop.id}")
            
            prompt = f"""
            You are the Devil's Advocate Risk Analyst for an options trading firm.
            Your job is to find flaws, tail risks, and reasons NOT to execute this trade.
            
            Market Context:
            - Underlying: {signal.underlying} @ ${signal.price}
            - Regime: {signal.regime.value}
            - Event Risks: {risk.events}
            
            Proposed Trade:
            - Strategy: {prop.strategy_type.value}
            - Max Profit: ${prop.max_profit*100:.2f}
            - Max Loss: ${prop.max_loss*100:.2f}
            - DTE: {prop.dte}
            - Proponent Thesis: {prop.thesis}
            
            Evaluate this trade. Be highly skeptical. If the risk/reward is poor, or if the strategy 
            mismatches the regime/events, vote DISAGREE.
            """
            
            try:
                response = self.structured_llm.invoke(prompt)
                vote = AgentVote(
                    agent_name="DevilsAdvocate",
                    vote=response.vote,
                    confidence=response.confidence,
                    reasoning=response.reasoning,
                    counter_arguments=response.counter_arguments
                )
            except Exception as e:
                logger.error(f"Devil's Advocate LLM failed: {e}")
                vote = AgentVote(
                    agent_name="DevilsAdvocate",
                    vote="DISAGREE",
                    confidence=1.0,
                    reasoning="API Error, defaulting to safe rejection.",
                    counter_arguments=["System error in LLM provider."]
                )
                
            votes.append(vote)
            
        return votes
