import numpy as np
from backend.models.market import Trend

def calculate_rsi(closes: list[float], period: int = 14) -> float:
    """Calculate Relative Strength Index (RSI)."""
    if len(closes) < period + 1:
        return 50.0  # Default neutral
        
    closes_array = np.array(closes)
    deltas = np.diff(closes_array)
    
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    if avg_loss == 0:
        return 100.0
        
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def calculate_sma(closes: list[float], period: int = 20) -> float:
    """Calculate Simple Moving Average."""
    if len(closes) < period:
        return np.mean(closes) if closes else 0.0
    return float(np.mean(closes[-period:]))

def calculate_bollinger_bands(closes: list[float], period: int = 20, std_dev: float = 2.0) -> tuple[float, float, float]:
    """Calculate Bollinger Bands (upper, middle, lower)."""
    if len(closes) < period:
        mid = np.mean(closes) if closes else 0.0
        return mid, mid, mid
        
    recent_closes = closes[-period:]
    sma = np.mean(recent_closes)
    std = np.std(recent_closes)
    
    upper = sma + (std_dev * std)
    lower = sma - (std_dev * std)
    
    return float(upper), float(sma), float(lower)

def detect_squeeze(bb_width_history: list[float], threshold: float = 0.10) -> bool:
    """
    Detect volatility squeeze. 
    bb_width_history is a list of (upper - lower) / middle.
    """
    if len(bb_width_history) < 2:
        return False
        
    current_width = bb_width_history[-1]
    # Simple squeeze detection: current width is less than threshold
    return current_width < threshold

def get_trend(close: float, sma: float) -> Trend:
    """Determine trend based on price vs SMA."""
    if close > sma * 1.01:
        return Trend.BULLISH
    elif close < sma * 0.99:
        return Trend.BEARISH
    return Trend.NEUTRAL
