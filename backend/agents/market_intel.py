import numpy as np
from datetime import datetime
from typing import Dict
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from backend.config import settings
from backend.models.market import MarketSignal, Regime, Trend
from backend.engine.indicators import calculate_rsi, calculate_sma, calculate_bollinger_bands, detect_squeeze, get_trend
from backend.engine.regime import classify_regime, detect_squeeze as detect_vix_squeeze
from backend.engine.iv_calculator import calculate_iv_rank, calculate_iv_percentile, load_iv_history, store_iv_snapshot
from backend.mcp.client import AlpacaClient
from backend.utils.logger import get_logger

logger = get_logger("market_intel")

class ThesisResponse(BaseModel):
    thesis: str = Field(description="A concise 2-sentence market thesis.")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0.")

class MarketIntelAgent:
    """Scans market, computes signals, and generates a thesis using Gemini."""
    
    def __init__(self):
        self.mcp = AlpacaClient()
        self.llm = ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL, 
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.2
        )
        self.structured_llm = self.llm.with_structured_output(ThesisResponse)
        
    def generate_signals(self, market_data: Dict = None, target_symbol: str = None) -> list[MarketSignal]:
        """
        Receives optional market data dict (for testing).
        If None, fetches real data from Alpaca MCP.
        Returns a list of MarketSignals.
        """
        signals = []
        underlyings = [target_symbol] if target_symbol else settings.WATCHED_UNDERLYINGS
        
        # Fetch real data for underlyings
        if market_data is None:
            # Get stock snapshots
            snapshots = self.mcp.get_stock_snapshots(underlyings)
            
            # Get VIX
            vix = self.mcp.get_vix_index()
            
            # Get historical bars for each underlying
            for symbol in underlyings:
                bars = self.mcp.get_stock_bars(symbol, days=60)
                closes = bars.get("closes", [])
                
                # Compute indicators
                rsi_14 = calculate_rsi(closes)
                sma_20 = calculate_sma(closes, 20)
                upper_bb, middle_bb, lower_bb = calculate_bollinger_bands(closes, 20)
                bb_width = (upper_bb - lower_bb) / middle_bb if middle_bb > 0 else 1.0
                bb_squeeze = bb_width < 0.10
                trend = get_trend(closes[-1] if closes else 0, sma_20)
                
                # Get current price
                current_price = snapshots.get(symbol, {}).get("price", closes[-1] if closes else 100.0)
                
                # Get option chain for IV data
                chain = self.mcp.get_option_chain(symbol)
                
                # Compute IV from ATM options
                atm_ivs = []
                for leg in chain.get("legs", []):
                    if abs(leg["strike"] - current_price) / current_price < 0.05:  # Within 5% ATM
                        if leg["iv"] > 0:
                            atm_ivs.append(leg["iv"])
                
                current_iv = np.mean(atm_ivs) if atm_ivs else 0.20
                
                # Load IV history and compute rank/percentile
                iv_history = load_iv_history(symbol)
                if iv_history:
                    iv_rank = calculate_iv_rank(current_iv, max(iv_history), min(iv_history))
                    iv_percentile = calculate_iv_percentile(current_iv, iv_history)
                else:
                    iv_rank = 0.5
                    iv_percentile = 0.5
                
                # Store current IV for future calculations
                store_iv_snapshot(symbol, current_iv)
                
                # Get VIX history for squeeze detection
                vix_history = load_iv_history("VIX")  # Using same storage for VIX
                if not vix_history:
                    # Create mock VIX history for now
                    vix_history = [vix] * 252
                vix_squeeze = detect_vix_squeeze(vix_history)
                
                # Classify regime
                regime = classify_regime(vix, iv_percentile, vix_squeeze, vix_history)
                
                # Generate thesis via LLM
                prompt = f"""
                Analyze the following options market data for {symbol}:
                - Price: ${current_price:.2f} (Trend vs SMA: {trend.value})
                - RSI(14): {rsi_14:.1f}
                - IV Rank: {iv_rank:.2f}, IV Percentile: {iv_percentile:.2f}
                - Current Regime: {regime.value}
                - VIX: {vix:.1f}
                
                Generate a concise, 2-sentence market thesis for trading options on this underlying today.
                """
                
                try:
                    response = self.structured_llm.invoke(prompt)
                    thesis = response.thesis
                    confidence = response.confidence
                except Exception as e:
                    logger.error(f"LLM thesis generation failed for {symbol}: {e}")
                    thesis = f"Default thesis due to API error. Trend is {trend.value}."
                    confidence = 0.5
                    
                signal = MarketSignal(
                    timestamp=datetime.now().isoformat(),
                    underlying=symbol,
                    price=current_price,
                    iv_current=current_iv,
                    iv_rank=iv_rank,
                    iv_percentile=iv_percentile,
                    regime=regime,
                    trend=trend,
                    thesis=thesis,
                    confidence=confidence
                )
                signals.append(signal)
        else:
            # Use provided mock data (for testing)
            for symbol, data in market_data.items():
                logger.info(f"Generating market intel for {symbol}")
                
                price = data.get("price", 100.0)
                sma = data.get("sma", 100.0)
                iv_current = data.get("iv_current", 0.20)
                iv_rank = data.get("iv_rank", 0.50)
                iv_percentile = data.get("iv_percentile", 0.50)
                regime = data.get("regime", Regime.NORMAL)
                
                trend = get_trend(price, sma)
                
                prompt = f"""
                Analyze the following options market data for {symbol}:
                - Price: ${price} (Trend vs SMA: {trend.value})
                - IV Rank: {iv_rank:.2f}, IV Percentile: {iv_percentile:.2f}
                - Current Regime: {regime.value}
                
                Generate a concise, 2-sentence market thesis for trading options on this underlying today.
                """
                
                try:
                    response = self.structured_llm.invoke(prompt)
                    thesis = response.thesis
                    confidence = response.confidence
                except Exception as e:
                    logger.error(f"LLM thesis generation failed for {symbol}: {e}")
                    thesis = f"Default thesis due to API error. Trend is {trend.value}."
                    confidence = 0.5
                    
                signal = MarketSignal(
                    timestamp=datetime.now().isoformat(),
                    underlying=symbol,
                    price=price,
                    iv_current=iv_current,
                    iv_rank=iv_rank,
                    iv_percentile=iv_percentile,
                    regime=regime,
                    trend=trend,
                    thesis=thesis,
                    confidence=confidence
                )
                signals.append(signal)
                
        return signals
