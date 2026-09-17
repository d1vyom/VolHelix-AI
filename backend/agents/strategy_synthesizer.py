import uuid
from typing import List, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from backend.config import settings
from backend.models.market import MarketSignal, RiskFlags, StrategyType, Trend
from backend.models.trade import TradeProposal
from backend.engine.regime import get_strategy_bias
from backend.engine.order_flow import analyze_order_flow, calculate_master_strategy_tp_sl
from backend.mcp.client import BinanceClient
from backend.utils.logger import get_logger

logger = get_logger("strategy_synthesizer")


class StrategySelection(BaseModel):
    strategy_type: StrategyType = Field(description="The selected crypto spot trading strategy.")
    reasoning: str = Field(description="Reasoning for selecting this strategy.")
    expected_win_rate: float = Field(description="Estimated win rate between 0.0 and 1.0.")


class StrategySynthesizerAgent:
    """Designs crypto spot trading strategies based on market intel and risk confluence."""
    
    def __init__(self):
        self.mcp = BinanceClient()
        self.llm = ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL, 
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.3
        )
        self.structured_llm = self.llm.with_structured_output(StrategySelection)
        
    def synthesize(self, signal: MarketSignal, risk: RiskFlags, option_chain=None) -> List[TradeProposal]:
        symbol = signal.symbol or signal.underlying or "BTCUSDT"
        logger.info(f"Synthesizing spot strategies for {symbol}")
        
        # 1. Get bias from volatility regime
        bias = get_strategy_bias(signal.regime)
        allowed_strategies = [s.value for s in bias["strategies"]]
        
        # 2. Select strategy via Gemini
        prompt = f"""
        Crypto Market Signal for {symbol}:
        - Price: ${signal.price:,.2f}
        - Trend: {signal.trend.value}
        - 24h Volatility Regime: {signal.regime.value}
        - Thesis: {signal.thesis}
        - Event Risks: {risk.events} (Risk Level: {risk.risk_level})
        
        Regime-Approved Strategies: {allowed_strategies}
        
        Select the single best strategy type from the approved list for these conditions.
        """
        
        try:
            selection = self.structured_llm.invoke(prompt)
            strat_type = selection.strategy_type
            thesis = selection.reasoning
        except Exception as e:
            logger.error(f"Strategy selection failed for {symbol}: {e}")
            strat_type = bias["strategies"][0]
            thesis = f"Selected {strat_type.value} based on {signal.regime.value} regime."
            
        proposals = self._build_spot_proposals(signal, strat_type, thesis)
        return proposals
    
    def _build_spot_proposals(self, signal: MarketSignal, strat_type: StrategyType, thesis: str) -> List[TradeProposal]:
        """Build spot trade proposals for crypto pairs."""
        symbol = signal.symbol or signal.underlying or "BTCUSDT"
        current_price = signal.price
        if current_price <= 0:
            current_price = self.mcp.get_price(symbol).get("price", 1000.0)
            
        # 1. Analyze order flow for dynamic TP/SL levels
        klines = self.mcp.get_klines(symbol, interval="1h", limit=50)
        order_flow = analyze_order_flow(symbol, klines)
        
        levels = calculate_master_strategy_tp_sl(
            symbol=symbol,
            current_price=current_price,
            order_flow=order_flow,
            gamma_profile=None,
            trend_bias=signal.trend.value
        )
        
        tp_price = levels.get("take_profit_price") or round(current_price * 1.05, 2)
        sl_price = levels.get("stop_loss_price") or round(current_price * 0.97, 2)
        
        # Sizing: default ~$200 USDT
        target_usdt = 200.0
        qty = round(target_usdt / current_price, 5) if current_price > 0 else 0.001
        
        max_profit = round((tp_price - current_price) * qty, 2)
        max_loss = round((current_price - sl_price) * qty, 2)
        ev = round(max_profit * 0.65 - max_loss * 0.35, 2)
        
        side = "BUY"
        if strat_type == StrategyType.SPOT_SHORT or strat_type == StrategyType.CASH:
            side = "SELL"
            
        proposal = TradeProposal(
            id=f"PROP-{uuid.uuid4().hex[:8].upper()}",
            symbol=symbol,
            underlying=symbol,
            strategy_type=strat_type,
            side=side,
            order_type="MARKET",
            qty=qty,
            quote_qty=target_usdt,
            entry_price=current_price,
            take_profit=tp_price,
            stop_loss=sl_price,
            max_profit=max_profit,
            max_loss=max_loss,
            breakevens=[round(current_price, 2)],
            ev=ev,
            thesis=f"{strat_type.value}: {thesis} (TP: ${tp_price:.2f}, SL: ${sl_price:.2f})",
            confidence=signal.confidence or 0.80
        )
        
        return [proposal]
