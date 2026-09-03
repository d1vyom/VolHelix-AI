import json
import os
from datetime import datetime
from typing import List
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from backend.config import settings
from backend.models.trade import TradeRecord
from backend.models.debate import PostMortem
from backend.utils.logger import get_logger

logger = get_logger("post_mortem")

# Store for strategy effectiveness scores per regime
STRATEGY_EFFECTIVENESS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "strategy_effectiveness.json")

class PostMortemResponse(BaseModel):
    regime_accuracy: bool = Field(description="Was the regime classification correct in hindsight?")
    strategy_score: int = Field(description="1-10 score on strategy selection quality.")
    lessons: list[str] = Field(description="Key takeaways from this trade.")

class PostMortemAgent:
    """Analyzes closed trades to extract lessons and improve future performance."""
    
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL, 
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.4
        )
        self.structured_llm = self.llm.with_structured_output(PostMortemResponse)
        self._load_effectiveness_scores()
        
    def _load_effectiveness_scores(self):
        """Load historical strategy effectiveness scores."""
        self.effectiveness_scores = {}
        if os.path.exists(STRATEGY_EFFECTIVENESS_FILE):
            try:
                with open(STRATEGY_EFFECTIVENESS_FILE, "r") as f:
                    self.effectiveness_scores = json.load(f)
            except Exception:
                pass
    
    def _save_effectiveness_scores(self):
        """Save updated effectiveness scores."""
        os.makedirs(os.path.dirname(STRATEGY_EFFECTIVENESS_FILE), exist_ok=True)
        try:
            with open(STRATEGY_EFFECTIVENESS_FILE, "w") as f:
                json.dump(self.effectiveness_scores, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save effectiveness scores: {e}")
    
    def _update_effectiveness(self, regime: str, strategy: str, score: int, pnl_diff: float):
        """Update rolling effectiveness scores."""
        key = f"{regime}:{strategy}"
        if key not in self.effectiveness_scores:
            self.effectiveness_scores[key] = {"total_score": 0, "count": 0, "total_pnl": 0.0}
        
        self.effectiveness_scores[key]["total_score"] += score
        self.effectiveness_scores[key]["count"] += 1
        self.effectiveness_scores[key]["total_pnl"] += pnl_diff
        self._save_effectiveness_scores()
    
    def get_effectiveness_summary(self) -> dict:
        """Get summary of strategy effectiveness by regime."""
        summary = {}
        for key, data in self.effectiveness_scores.items():
            if data["count"] > 0:
                avg_score = data["total_score"] / data["count"]
                avg_pnl = data["total_pnl"] / data["count"]
                summary[key] = {
                    "avg_score": round(avg_score, 2),
                    "avg_pnl": round(avg_pnl, 2),
                    "sample_size": data["count"]
                }
        return summary
    
    def get_recent_lessons(self, limit: int = 5) -> List[str]:
        """Get recent lessons for context injection."""
        all_lessons = []
        for key in sorted(self.effectiveness_scores.keys(), reverse=True):
            # This is a simplified version - in reality we'd store lessons separately
            pass
        return all_lessons[:limit]
        
    def analyze(self, closed_trade: TradeRecord) -> PostMortem:
        logger.info(f"Running post-mortem on closed trade {closed_trade.trade_id}")
        
        prompt = f"""
        Analyze this closed options trade:
        - Underlying: {closed_trade.proposal.underlying}
        - Strategy: {closed_trade.proposal.strategy_type.value}
        - Regime at Entry: {closed_trade.proposal.regime_at_entry.value if hasattr(closed_trade.proposal, 'regime_at_entry') else 'UNKNOWN'}
        - Original Thesis: {closed_trade.proposal.thesis}
        - Expected Value at Entry: ${closed_trade.proposal.ev:.2f}
        - Actual Realized P&L: ${closed_trade.realized_pnl:.2f}
        - DTE at Entry: {closed_trade.proposal.dte}
        
        Provide a post-mortem analysis. 
        1. Was the regime classification correct in hindsight? (true/false)
        2. Score the strategy selection quality 1-10.
        3. List 2-3 key lessons learned.
        """
        
        try:
            res = self.structured_llm.invoke(prompt)
            pnl_diff = closed_trade.realized_pnl - closed_trade.proposal.ev
            pm = PostMortem(
                trade_id=closed_trade.trade_id,
                actual_pnl=closed_trade.realized_pnl,
                expected_pnl=closed_trade.proposal.ev,
                pnl_diff=pnl_diff,
                regime_was_correct=res.regime_accuracy,
                strategy_score=res.strategy_score,
                lessons=res.lessons
            )
            
            # Update effectiveness scores
            regime = closed_trade.proposal.regime_at_entry.value if hasattr(closed_trade.proposal, 'regime_at_entry') else "UNKNOWN"
            strategy = closed_trade.proposal.strategy_type.value
            self._update_effectiveness(regime, strategy, res.strategy_score, pnl_diff)
            
        except Exception as e:
            logger.error(f"Post-mortem LLM failed: {e}")
            pnl_diff = closed_trade.realized_pnl - closed_trade.proposal.ev
            pm = PostMortem(
                trade_id=closed_trade.trade_id,
                actual_pnl=closed_trade.realized_pnl,
                expected_pnl=closed_trade.proposal.ev,
                pnl_diff=pnl_diff,
                regime_was_correct=True,
                strategy_score=5,
                lessons=["Error generating lessons."]
            )
            
        return pm
