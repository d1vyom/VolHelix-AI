import numpy as np
from datetime import datetime
from typing import Dict, List, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from backend.config import settings
from backend.models.market import MarketSignal, Regime, Trend
from backend.engine.indicators import calculate_rsi, calculate_sma, calculate_bollinger_bands, get_trend
from backend.engine.regime import realized_volatility, detect_squeeze, classify_crypto_regime
from backend.mcp.client import BinanceClient
from backend.utils.logger import get_logger

logger = get_logger("market_intel")


class ThesisResponse(BaseModel):
    thesis: str = Field(description="A concise 2-sentence crypto spot market thesis.")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0.")


class MarketIntelAgent:
    """
    Analyzes live Binance crypto market data, computes indicators & volatility regimes,
    and synthesizes an actionable thesis using Gemini.
    """
    
    def __init__(self):
        self.mcp = BinanceClient()
        self.llm = ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL, 
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.2
        )
        self.structured_llm = self.llm.with_structured_output(ThesisResponse)
        
    def generate_signals(self, market_data: Optional[Dict] = None, target_symbol: Optional[str] = None) -> List[MarketSignal]:
        """
        Generates MarketSignals for watched crypto pairs.
        Uses real production Binance market data if market_data is None.
        """
        signals = []
        symbols = [target_symbol] if target_symbol else settings.WATCHED_SYMBOLS
        
        if market_data is None:
            for symbol in symbols:
                try:
                    ticker24 = self.mcp.get_24hr_ticker(symbol)
                    klines = self.mcp.get_klines(symbol, interval="1h", limit=60)
                    
                    closes = [k["close"] for k in klines] if klines else []
                    highs = [k["high"] for k in klines] if klines else []
                    lows = [k["low"] for k in klines] if klines else []
                    
                    current_price = ticker24.get("last_price") or (closes[-1] if closes else 0.0)
                    price_change_24h = ticker24.get("price_change_pct", 0.0)
                    volume_24h = ticker24.get("quote_volume", 0.0)
                    
                    # Compute technical indicators
                    rsi_14 = calculate_rsi(closes) if len(closes) >= 15 else 50.0
                    sma_20 = calculate_sma(closes, 20) if len(closes) >= 20 else current_price
                    trend = get_trend(current_price, sma_20)
                    
                    # Squeeze detection on closes
                    squeeze = detect_squeeze(closes, period=20) if len(closes) >= 20 else False
                    
                    # Realized volatility (annualized %)
                    current_vol = realized_volatility(closes, window=30) if len(closes) >= 31 else 45.0
                    vol_rank = min(1.0, max(0.0, (current_vol - 20.0) / 80.0))
                    vol_percentile = vol_rank
                    
                    # Classify crypto regime
                    regime = classify_crypto_regime(
                        btc_realized_vol_30d=current_vol,
                        vol_percentile=vol_percentile,
                        squeeze_detected=squeeze
                    )
                    
                    # Generate concise thesis via Gemini
                    prompt = f"""
                    Analyze the following crypto spot market data for {symbol}:
                    - Price: ${current_price:,.2f} (24h Change: {price_change_24h:+.2f}%)
                    - Trend vs 20 SMA: {trend.value}
                    - RSI(14): {rsi_14:.1f}
                    - Realized Volatility (Annualized): {current_vol:.1f}%
                    - Volatility Regime: {regime.value}
                    
                    Generate a concise, 2-sentence market thesis for spot trading this pair today.
                    """
                    
                    try:
                        response = self.structured_llm.invoke(prompt)
                        thesis = response.thesis
                        confidence = response.confidence
                    except Exception as e:
                        logger.error(f"LLM thesis generation failed for {symbol}: {e}")
                        thesis = f"{symbol} is trading at ${current_price:,.2f} with a {trend.value.lower()} trend. Volatility regime is {regime.value}."
                        confidence = 0.70
                        
                    signal = MarketSignal(
                        timestamp=datetime.now().isoformat(),
                        symbol=symbol,
                        underlying=symbol,
                        price=current_price,
                        price_change_24h=price_change_24h,
                        volume_24h=volume_24h,
                        high_24h=ticker24.get("high", 0.0),
                        low_24h=ticker24.get("low", 0.0),
                        iv_current=current_vol,
                        iv_rank=vol_rank,
                        iv_percentile=vol_percentile,
                        regime=regime,
                        trend=trend,
                        thesis=thesis,
                        confidence=confidence
                    )
                    signals.append(signal)
                except Exception as ex:
                    logger.error(f"Failed generating market intel for {symbol}: {ex}")
        else:
            for symbol, data in market_data.items():
                price = data.get("price", 1000.0)
                sma = data.get("sma", 1000.0)
                trend = get_trend(price, sma)
                regime = data.get("regime", Regime.NORMAL)
                
                signals.append(MarketSignal(
                    timestamp=datetime.now().isoformat(),
                    symbol=symbol,
                    underlying=symbol,
                    price=price,
                    price_change_24h=data.get("change_pct", 0.0),
                    volume_24h=data.get("volume", 0.0),
                    iv_current=data.get("iv_current", 45.0),
                    iv_rank=data.get("iv_rank", 0.5),
                    iv_percentile=data.get("iv_percentile", 0.5),
                    regime=regime,
                    trend=trend,
                    thesis=f"Simulated test data for {symbol}.",
                    confidence=0.8
                ))
                
        return signals
