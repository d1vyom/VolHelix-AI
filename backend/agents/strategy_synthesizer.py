import uuid
import numpy as np
from typing import List
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from backend.config import settings
from backend.models.market import MarketSignal, RiskFlags, StrategyType, OptionLeg, Trend
from backend.models.trade import TradeProposal
from backend.engine.regime import get_strategy_bias
from backend.engine.strategy_builder import (
    build_bull_put_spread,
    build_bear_call_spread,
    build_iron_condor,
    build_master_order_flow_strategy
)
from backend.engine.order_flow import analyze_order_flow
from backend.engine.gamma_profile import calculate_gamma_profile
from backend.mcp.client import AlpacaClient
from backend.utils.logger import get_logger

logger = get_logger("strategy_synthesizer")

class StrategySelection(BaseModel):
    strategy_type: StrategyType = Field(description="The selected options strategy.")
    reasoning: str = Field(description="Reasoning for selecting this strategy.")
    expected_win_rate: float = Field(description="Estimated win rate (0-1).")

class StrategySynthesizerAgent:
    """Designs options strategies based on market intel and event risks."""
    
    def __init__(self):
        self.mcp = AlpacaClient()
        self.llm = ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL, 
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.3
        )
        self.structured_llm = self.llm.with_structured_output(StrategySelection)
        
    def synthesize(self, signal: MarketSignal, risk: RiskFlags, option_chain: list[OptionLeg] = None) -> List[TradeProposal]:
        logger.info(f"Synthesizing strategies for {signal.underlying}")
        
        # 1. Get bias from regime
        bias = get_strategy_bias(signal.regime)
        allowed_strategies = [s.value for s in bias["strategies"]]
        
        # 2. Fetch real option chain if not provided
        if option_chain is None or len(option_chain) == 0:
            chain_data = self.mcp.get_option_chain(signal.underlying)
            option_chain = []
            for leg in chain_data.get("legs", []):
                strike = float(leg.get("strike", 0.0) or 0.0)
                raw_delta = float(leg.get("delta", 0.0) or 0.0)
                c_type = leg.get("type", "CALL").upper()
                if raw_delta == 0.0 and signal.price > 0 and strike > 0:
                    if c_type == "CALL":
                        raw_delta = max(0.05, min(0.95, 0.50 - (strike - signal.price) / (signal.price * 0.15) * 0.40))
                    else:
                        raw_delta = max(-0.95, min(-0.05, -0.50 + (signal.price - strike) / (signal.price * 0.15) * 0.40))

                raw_oi = int(leg.get("open_interest", 0) or 0)
                effective_oi = raw_oi if raw_oi >= 100 else 500

                option_chain.append(OptionLeg(
                    action=leg.get("action", "BUY"),
                    contract_type=c_type,
                    strike=strike,
                    expiry=leg["expiry"],
                    symbol=leg["symbol"],
                    premium=(leg["bid"] + leg["ask"]) / 2 if leg["bid"] > 0 and leg["ask"] > 0 else leg["premium"] if leg.get("premium") else 0,
                    delta=raw_delta,
                    gamma=leg.get("gamma", 0),
                    theta=leg.get("theta", 0),
                    vega=leg.get("vega", 0),
                    oi=effective_oi,
                    bid=leg.get("bid", 0),
                    ask=leg.get("ask", 0)
                ))
        
        # Filter by liquidity: require positive bid/ask and positive strike
        option_chain = [leg for leg in option_chain if leg.oi >= 100 and leg.bid > 0 and leg.ask > 0 and leg.strike > 0]
        
        # 3. Ask LLM to pick the absolute best strategy for the current context
        prompt = f"""
        Market Signal for {signal.underlying}:
        - Trend: {signal.trend.value}
        - Regime: {signal.regime.value}
        - Thesis: {signal.thesis}
        - Event Risks: {risk.events} (Risk Level: {risk.risk_level})
        
        Available Regime-Approved Strategies: {allowed_strategies}
        
        Select the single best strategy type from the approved list for these conditions.
        """
        
        try:
            selection = self.structured_llm.invoke(prompt)
            strat_type = selection.strategy_type
            thesis = selection.reasoning
        except Exception as e:
            logger.error(f"Strategy selection failed: {e}")
            strat_type = bias["strategies"][0]
            thesis = "Fallback strategy selection due to LLM error."
            
        proposals = []
        
        # 4. Build the proposal using real option chain data
        proposals = self._build_proposals(signal, strat_type, option_chain, thesis)
        
        return proposals
    
    def _build_proposals(self, signal: MarketSignal, strat_type: StrategyType, option_chain: List[OptionLeg], thesis: str) -> List[TradeProposal]:
        """Build trade proposals from real option chain data."""
        proposals = []
        current_price = signal.price
        
        # Group by expiration
        by_expiry = {}
        for leg in option_chain:
            if leg.expiry not in by_expiry:
                by_expiry[leg.expiry] = {"calls": [], "puts": []}
            if leg.contract_type == "CALL":
                by_expiry[leg.expiry]["calls"].append(leg)
            else:
                by_expiry[leg.expiry]["puts"].append(leg)
        
        # Sort by expiry
        sorted_expiries = sorted(by_expiry.keys())
        
        for expiry in sorted_expiries:
            calls = sorted(by_expiry[expiry]["calls"], key=lambda x: x.strike)
            puts = sorted(by_expiry[expiry]["puts"], key=lambda x: x.strike)
            
            if not calls or not puts:
                continue
            
            # Calculate DTE
            from datetime import datetime
            dte = (datetime.fromisoformat(expiry) - datetime.now()).days
            if dte < 3 or dte > 60:
                continue
            
            # Find ATM strikes
            atm_call = min(calls, key=lambda x: abs(x.strike - current_price))
            atm_put = min(puts, key=lambda x: abs(x.strike - current_price))
            
            if strat_type == StrategyType.MASTER_ORDER_FLOW:
                # 1. Fetch recent bars for Order Block & FVG analysis
                bars_res = self.mcp.get_stock_bars(signal.underlying, days=20)
                bars = bars_res.get("bars", [])
                order_flow = analyze_order_flow(signal.underlying, bars)
                
                # 2. Compute Gamma Profile (GEX)
                raw_legs = [l.model_dump() for l in option_chain]
                gamma_prof = calculate_gamma_profile(raw_legs, current_price)
                
                bullish_anchor = order_flow.nearest_bullish_ob.low if order_flow.nearest_bullish_ob else gamma_prof.put_wall
                bearish_anchor = order_flow.nearest_bearish_ob.high if order_flow.nearest_bearish_ob else gamma_prof.call_wall
                
                if order_flow.trend_bias in ["BULLISH", "NEUTRAL"]:
                    # Anchor short put strictly at or below Bullish OB and Put Wall
                    target_short_strike = min(bullish_anchor, gamma_prof.put_wall, current_price * 0.98)
                    short_candidates = [p for p in puts if p.strike <= target_short_strike]
                    if not short_candidates:
                        short_candidates = [p for p in puts if p.strike < current_price]
                    if short_candidates:
                        short_put = max(short_candidates, key=lambda x: x.strike)
                        long_candidates = [p for p in puts if p.strike < short_put.strike]
                        if long_candidates:
                            long_put = min(long_candidates, key=lambda x: abs(x.strike - (short_put.strike - 5.0)))
                            net_credit = short_put.premium - long_put.premium
                            spread_width = short_put.strike - long_put.strike
                            max_loss = max(0.01, spread_width - net_credit)
                            be = short_put.strike - net_credit
                            tp = round(net_credit * 0.50, 2)
                            sl = round(net_credit * 1.50, 2)
                            thesis_desc = f"Master Order Flow: Anchored outside Bullish OB (${short_put.strike}) & Put Wall (${gamma_prof.put_wall})."
                            proposal = build_master_order_flow_strategy(
                                underlying=signal.underlying,
                                legs=[short_put, long_put],
                                is_credit=True,
                                net_premium=net_credit,
                                max_profit=net_credit,
                                max_loss=max_loss,
                                breakevens=[be],
                                dte=dte,
                                thesis=thesis_desc,
                                take_profit=tp,
                                stop_loss=sl
                            )
                            proposal.ev = self._calculate_ev(proposal)
                            proposals.append(proposal)
                else:
                    target_short_strike = max(bearish_anchor, gamma_prof.call_wall, current_price * 1.02)
                    short_candidates = [c for c in calls if c.strike >= target_short_strike]
                    if not short_candidates:
                        short_candidates = [c for c in calls if c.strike > current_price]
                    if short_candidates:
                        short_call = min(short_candidates, key=lambda x: x.strike)
                        long_candidates = [c for c in calls if c.strike > short_call.strike]
                        if long_candidates:
                            long_call = min(long_candidates, key=lambda x: abs(x.strike - (short_call.strike + 5.0)))
                            net_credit = short_call.premium - long_call.premium
                            spread_width = long_call.strike - short_call.strike
                            max_loss = max(0.01, spread_width - net_credit)
                            be = short_call.strike + net_credit
                            tp = round(net_credit * 0.50, 2)
                            sl = round(net_credit * 1.50, 2)
                            thesis_desc = f"Master Order Flow: Anchored outside Bearish OB (${short_call.strike}) & Call Wall (${gamma_prof.call_wall})."
                            proposal = build_master_order_flow_strategy(
                                underlying=signal.underlying,
                                legs=[short_call, long_call],
                                is_credit=True,
                                net_premium=net_credit,
                                max_profit=net_credit,
                                max_loss=max_loss,
                                breakevens=[be],
                                dte=dte,
                                thesis=thesis_desc,
                                take_profit=tp,
                                stop_loss=sl
                            )
                            proposal.ev = self._calculate_ev(proposal)
                            proposals.append(proposal)

            elif strat_type == StrategyType.BULL_PUT_SPREAD:
                short_puts = [p for p in puts if p.strike < current_price and -0.40 < p.delta < -0.05]
                if not short_puts:
                    short_puts = [p for p in puts if p.strike < current_price]
                if short_puts:
                    short_put = min(short_puts, key=lambda x: abs(x.strike - current_price * 0.97))
                    long_puts = [p for p in puts if p.strike < short_put.strike]
                    if long_puts:
                        long_put = min(long_puts, key=lambda x: abs(x.strike - (short_put.strike - 5.0)))
                        proposal = build_bull_put_spread(signal.underlying, short_put, long_put, expiry, dte, thesis)
                        proposal.ev = self._calculate_ev(proposal)
                        proposals.append(proposal)
            
            elif strat_type == StrategyType.BEAR_CALL_SPREAD:
                short_calls = [c for c in calls if c.strike > current_price and 0.05 < c.delta < 0.40]
                if not short_calls:
                    short_calls = [c for c in calls if c.strike > current_price]
                if short_calls:
                    short_call = min(short_calls, key=lambda x: abs(x.strike - current_price * 1.03))
                    long_calls = [c for c in calls if c.strike > short_call.strike]
                    if long_calls:
                        long_call = min(long_calls, key=lambda x: abs(x.strike - (short_call.strike + 5.0)))
                        proposal = build_bear_call_spread(signal.underlying, short_call, long_call, expiry, dte, thesis)
                        proposal.ev = self._calculate_ev(proposal)
                        proposals.append(proposal)
            
            elif strat_type == StrategyType.IRON_CONDOR:
                put_spread = self._find_put_spread(puts, current_price)
                call_spread = self._find_call_spread(calls, current_price)
                if put_spread and call_spread:
                    short_put, long_put = put_spread
                    short_call, long_call = call_spread
                    proposal = build_iron_condor(signal.underlying, short_put, long_put, short_call, long_call, expiry, dte, thesis)
                    proposal.ev = self._calculate_ev(proposal)
                    proposals.append(proposal)
            
            elif strat_type == StrategyType.LONG_STRADDLE:
                # Buy ATM call and put
                if atm_call.oi >= 100 and atm_put.oi >= 100:
                    call_leg = OptionLeg(action="BUY", contract_type="CALL", strike=atm_call.strike, expiry=expiry,
                                        symbol=atm_call.symbol, premium=atm_call.premium, delta=atm_call.delta,
                                        gamma=atm_call.gamma, theta=atm_call.theta, vega=atm_call.vega,
                                        oi=atm_call.oi, bid=atm_call.bid, ask=atm_call.ask)
                    put_leg = OptionLeg(action="BUY", contract_type="PUT", strike=atm_put.strike, expiry=expiry,
                                       symbol=atm_put.symbol, premium=atm_put.premium, delta=atm_put.delta,
                                       gamma=atm_put.gamma, theta=atm_put.theta, vega=atm_put.vega,
                                       oi=atm_put.oi, bid=atm_put.bid, ask=atm_put.ask)
                    proposal = self._build_straddle(signal.underlying, call_leg, put_leg, expiry, dte, thesis)
                    proposal.ev = self._calculate_ev(proposal)
                    proposals.append(proposal)
        
        # If proposals is still empty, build a baseline spread from available contracts
        if not proposals and sorted_expiries:
            from datetime import datetime
            for expiry in sorted_expiries:
                calls = sorted(by_expiry[expiry]["calls"], key=lambda x: x.strike)
                puts = sorted(by_expiry[expiry]["puts"], key=lambda x: x.strike)
                dte = max(3, (datetime.fromisoformat(expiry) - datetime.now()).days)
                otm_puts = [p for p in puts if p.strike < current_price]
                if len(otm_puts) >= 2:
                    sp = otm_puts[-1]
                    lp = otm_puts[0]
                    prop = build_bull_put_spread(signal.underlying, sp, lp, expiry, dte, thesis)
                    prop.ev = self._calculate_ev(prop)
                    proposals.append(prop)
                    break

        # Sort by EV descending and return top 3
        proposals.sort(key=lambda p: p.ev, reverse=True)
        return proposals[:3]
    
    def _find_put_spread(self, puts: List[OptionLeg], current_price: float):
        """Find a suitable OTM put spread for iron condor."""
        short_candidates = [p for p in puts if p.strike < current_price * 0.98 and -0.35 < p.delta < -0.05]
        if not short_candidates:
            short_candidates = [p for p in puts if p.strike < current_price * 0.98]
        if not short_candidates:
            return None
        short_put = min(short_candidates, key=lambda x: abs(x.strike - current_price * 0.96))
        
        long_candidates = [p for p in puts if p.strike < short_put.strike]
        if not long_candidates:
            return None
        long_put = min(long_candidates, key=lambda x: abs(x.strike - (short_put.strike - 5.0)))
        
        return (short_put, long_put)
    
    def _find_call_spread(self, calls: List[OptionLeg], current_price: float):
        """Find a suitable OTM call spread for iron condor."""
        short_candidates = [c for c in calls if c.strike > current_price * 1.02 and 0.05 < c.delta < 0.35]
        if not short_candidates:
            short_candidates = [c for c in calls if c.strike > current_price * 1.02]
        if not short_candidates:
            return None
        short_call = min(short_candidates, key=lambda x: abs(x.strike - current_price * 1.04))
        
        long_candidates = [c for c in calls if c.strike > short_call.strike]
        if not long_candidates:
            return None
        long_call = min(long_candidates, key=lambda x: abs(x.strike - (short_call.strike + 5.0)))
        
        return (short_call, long_call)
    
    def _build_straddle(self, underlying: str, call_leg: OptionLeg, put_leg: OptionLeg, expiry: str, dte: int, thesis: str) -> TradeProposal:
        """Build a long straddle proposal."""
        total_debit = call_leg.premium + put_leg.premium
        net_delta = call_leg.delta + put_leg.delta
        net_theta = call_leg.theta + put_leg.theta
        net_vega = call_leg.vega + put_leg.vega
        
        return TradeProposal(
            id=str(uuid.uuid4()),
            underlying=underlying,
            strategy_type=StrategyType.LONG_STRADDLE,
            legs=[call_leg, put_leg],
            is_credit=False,
            net_premium=-total_debit,
            max_profit=float('inf'),
            max_loss=total_debit,
            breakevens=[call_leg.strike - total_debit, call_leg.strike + total_debit],
            net_delta=net_delta,
            net_theta=net_theta,
            net_vega=net_vega,
            dte=dte,
            ev=0.0,
            thesis=thesis
        )
    
    def _calculate_ev(self, proposal: TradeProposal) -> float:
        """Calculate expected value of a proposal."""
        # Simplified EV calculation
        # For credit spreads: EV = credit * prob_profit - max_loss * prob_loss
        # Assume win rate based on delta
        if proposal.is_credit:
            # Approximate win rate from delta (for credit spreads)
            win_rate = 1.0 - abs(proposal.net_delta)  # Rough approximation
            win_rate = max(0.4, min(0.85, win_rate))  # Clamp
            avg_win = proposal.max_profit
            avg_loss = proposal.max_loss
            return (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        else:
            # Debit strategies
            win_rate = 0.5  # 50/50 for straddles
            avg_win = proposal.max_profit if proposal.max_profit != float('inf') else proposal.net_premium * 2
            avg_loss = proposal.max_loss
            return (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
