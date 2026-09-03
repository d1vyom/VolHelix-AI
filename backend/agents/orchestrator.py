import asyncio
import numpy as np
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

from backend.config import settings
from backend.utils.logger import get_logger

from backend.mcp.client import AlpacaClient
from backend.agents.market_intel import MarketIntelAgent
from backend.agents.event_scanner import EventScanner
from backend.agents.strategy_synthesizer import StrategySynthesizerAgent
from backend.agents.devils_advocate import DevilsAdvocateAgent
from backend.agents.executor import ExecutionAgent
from backend.agents.consensus import evaluate_consensus
from backend.risk.risk_gate import RiskGate
from backend.agents.regime_engine import RegimeEngine
from backend.agents.post_mortem import PostMortemAgent

from backend.models.market import MarketSignal, RiskFlags, Regime
from backend.models.trade import TradeProposal, TradeRecord
from backend.models.debate import AgentVote, DebateResult, PostMortem
from backend.store.postmortem_store import postmortem_store
from backend.models.risk import RiskGateResult

from backend.store.portfolio_store import portfolio_store
from backend.store.trade_log import trade_log

logger = get_logger("orchestrator")

# 1. Define State
class TradingState(TypedDict):
    underlying: str
    market_data: dict
    signal: MarketSignal
    risk_flags: RiskFlags
    proposals: List[TradeProposal]
    votes: List[AgentVote]
    debate_result: DebateResult
    risk_result: RiskGateResult
    regime: Regime
    postmortem_result: PostMortem

class TradingOrchestrator:
    def __init__(self):
        self.mcp = AlpacaClient()
        self.market_intel = MarketIntelAgent()
        self.event_scanner = EventScanner()
        self.synthesizer = StrategySynthesizerAgent()
        self.devils_advocate = DevilsAdvocateAgent()
        self.regime_engine = RegimeEngine()
        self.post_mortem = PostMortemAgent()
        self.executor = ExecutionAgent(self.mcp)
        self.risk_gate = RiskGate()
        self.graph = self._build_graph()
        
    def _build_graph(self):
        workflow = StateGraph(TradingState)
        
        workflow.add_node("intel_and_risk", self._node_intel_and_risk)
        workflow.add_node("regime", self._node_regime)
        workflow.add_node("strategize", self._node_strategize)
        workflow.add_node("debate", self._node_debate)
        workflow.add_node("risk_check", self._node_risk_check)
        workflow.add_node("execute", self._node_execute)
        
        workflow.set_entry_point("intel_and_risk")
        workflow.add_edge("intel_and_risk", "regime")
        workflow.add_edge("regime", "strategize")
        workflow.add_edge("strategize", "debate")
        
        # Conditional edge after debate
        def check_consensus(state: TradingState):
            if state["debate_result"].consensus_reached:
                return "risk_check"
            return END
            
        workflow.add_conditional_edges("debate", check_consensus, {"risk_check": "risk_check", END: END})
        
        # Conditional edge after risk gate
        def check_risk_gate(state: TradingState):
            if state["risk_result"].approved:
                return "execute"
            return END
            
        workflow.add_conditional_edges("risk_check", check_risk_gate, {"execute": "execute", END: END})
        workflow.add_node("postmortem", self._node_postmortem)
        workflow.add_edge("execute", "postmortem")
        workflow.add_edge("postmortem", END)
        
        return workflow.compile()

    # --- Node Functions ---
    def _node_intel_and_risk(self, state: TradingState) -> Dict:
        logger.info(f"[{state['underlying']}] Running Market Intel & Event Scan")
        signals = self.market_intel.generate_signals(target_symbol=state['underlying'])
        signal = next((s for s in signals if s.underlying == state['underlying']), None)
        if signal is None and signals:
            signal = signals[0]
        elif signal is None:
            logger.warning(f"[{state['underlying']}] No market signal generated, skipping cycle")
            raise RuntimeError(f"No market signal for {state['underlying']}")

        flags = self.event_scanner.scan_risks(state['underlying'])
        return {"signal": signal, "risk_flags": flags}
        
    def _node_regime(self, state: TradingState) -> Dict:
        """Classify the market regime based on the signal and store it in state."""
        logger.info(f"[{state['underlying']}] Classifying regime")
        regime = self.regime_engine.classify(state['signal'])
        return {"regime": regime}

    def _node_strategize(self, state: TradingState) -> Dict:
        logger.info(f"[{state['underlying']}] Synthesizing Strategies")
        proposals = self.synthesizer.synthesize(state["signal"], state["risk_flags"], [])
        return {"proposals": proposals}
        
    def _node_debate(self, state: TradingState) -> Dict:
        logger.info(f"[{state['underlying']}] Running Devil's Advocate Debate")
        proposals = state.get("proposals", [])
        if not proposals:
            logger.warning(f"[{state['underlying']}] No proposals generated for debate.")
            result = DebateResult(
                winning_proposal_id="",
                consensus_reached=False,
                summary="No valid proposals generated to debate.",
                votes=[]
            )
            return {"votes": [], "debate_result": result}
        
        # 1. Devil's Advocate Votes
        da_votes = self.devils_advocate.evaluate(proposals, state["signal"], state["risk_flags"])
        
        # 2. Strategy Agent implicitly votes YES for its own top proposal
        strat_vote = AgentVote(agent_name="StrategySynthesizer", vote="AGREE", confidence=0.9, reasoning="My best idea.", counter_arguments=[])
        
        # 3. Market Intel votes YES if trend aligns with strategy
        intel_vote = AgentVote(agent_name="MarketIntel", vote="AGREE", confidence=0.8, reasoning="Aligns with thesis.", counter_arguments=[])
        
        all_votes = da_votes + [strat_vote, intel_vote]
        
        # Evaluate consensus (weights defined here)
        weights = {"StrategySynthesizer": 0.4, "DevilsAdvocate": 0.4, "MarketIntel": 0.2}
        result = evaluate_consensus(proposals[0].id, all_votes, weights)
        
        logger.info(f"[{state['underlying']}] Consensus Result: {result.summary}")
        return {"votes": all_votes, "debate_result": result}

        
    def _node_risk_check(self, state: TradingState) -> Dict:
        logger.info(f"[{state['underlying']}] Running Deterministic Risk Gate")
        
        # Get winning proposal
        winning_prop = next((p for p in state["proposals"] if p.id == state["debate_result"].winning_proposal_id), None)
        if not winning_prop:
            return {"risk_result": RiskGateResult(approved=False, reason="No winning proposal found", timestamp="")}
            
        snapshot = portfolio_store.get_snapshot()
        risk_result = self.risk_gate.evaluate(winning_prop, snapshot)
        
        logger.info(f"[{state['underlying']}] Risk Gate: {'APPROVED' if risk_result.approved else 'REJECTED - ' + str(risk_result.reason)}")
        return {"risk_result": risk_result}
        
    def _node_postmortem(self, state: TradingState) -> Dict:
        """Generate a post-mortem analysis for the executed trade, persist it, and return."""
        logger.info(f"[{state['underlying']}] Generating post-mortem analysis")
        trade_record = state.get('trade_record')
        if not trade_record:
            logger.warning(f"[{state['underlying']}] No trade_record found for postmortem")
            return {"postmortem_result": None}
        result = self.post_mortem.analyze(trade_record)
        # Fire-and-forget persistence in a background thread (works in sync context)
        import threading
        def _save():
            import asyncio as _asyncio
            _asyncio.run(postmortem_store.save(result))
        threading.Thread(target=_save, daemon=True).start()
        return {"postmortem_result": result}

    def _node_execute(self, state: TradingState) -> Dict:
        logger.info(f"[{state['underlying']}] Executing Trade!")
        debate_res = state.get("debate_result")
        winning_id = debate_res.winning_proposal_id if debate_res else ""
        winning_prop = next((p for p in state.get("proposals", []) if p.id == winning_id), None)
        if not winning_prop:
            logger.warning(f"[{state['underlying']}] No winning proposal found to execute.")
            return {"trade_record": None}
        
        record = self.executor.execute(winning_prop, state["risk_result"])
        
        # Fire-and-forget persistence in a background thread (works in sync context)
        import threading
        def _save():
            import asyncio as _asyncio
            _asyncio.run(trade_log.save_trade(record))
        threading.Thread(target=_save, daemon=True).start()
        
        # Update portfolio store in memory
        portfolio_store.add_position(record) # Note: add_position needs implementing in portfolio_store
        
        return {"trade_record": record}
        
    def run_cycle(self, underlying: str):
        """Runs one full autonomous cycle for a given underlying."""
        print(f"\n{'='*50}\nStarting Autonomous Cycle for {underlying}\n{'='*50}")
        
        # Use real market data fetching - the agent will fetch it
        market_data = {}
        
        initial_state = {
            "underlying": underlying,
            "market_data": market_data
        }
        
        result = self.graph.invoke(initial_state)
        print(f"\nCycle Complete for {underlying}. Result state keys: {result.keys()}\n")
        return result
