import json
import os
from datetime import datetime
from backend.utils.logger import get_logger

logger = get_logger("iv_calculator")
IV_HISTORY_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "iv_history")

def calculate_iv_rank(current_iv: float, iv_high_52w: float, iv_low_52w: float) -> float:
    """
    Calculate IV Rank (0.0 to 1.0).
    Formula: (Current IV - 52w Low) / (52w High - 52w Low)
    """
    if iv_high_52w <= iv_low_52w:
        return 0.5
    
    rank = (current_iv - iv_low_52w) / (iv_high_52w - iv_low_52w)
    return max(0.0, min(1.0, rank))

def calculate_iv_percentile(current_iv: float, historical_ivs: list[float]) -> float:
    """
    Calculate IV Percentile (0.0 to 1.0).
    Percentage of days in the past year where IV was lower than current IV.
    """
    if not historical_ivs:
        return 0.5
        
    days_lower = sum(1 for iv in historical_ivs if iv < current_iv)
    return days_lower / len(historical_ivs)

def store_iv_snapshot(underlying: str, iv: float, date: str = None):
    """Store daily IV snapshot for future rank/percentile calculations."""
    os.makedirs(IV_HISTORY_DIR, exist_ok=True)
    file_path = os.path.join(IV_HISTORY_DIR, f"{underlying}.json")
    
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
        
    data = {}
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            try:
                data = json.load(f)
            except:
                pass
                
    data[date] = iv
    
    with open(file_path, "w") as f:
        json.dump(data, f)
        
def load_iv_history(underlying: str, days: int = 252) -> list[float]:
    """Load historical IV values, up to a specified number of days."""
    file_path = os.path.join(IV_HISTORY_DIR, f"{underlying}.json")
    
    if not os.path.exists(file_path):
        return []
        
    with open(file_path, "r") as f:
        try:
            data = json.load(f)
            # Sort by date and take the last 'days' values
            sorted_dates = sorted(data.keys())
            recent_dates = sorted_dates[-days:]
            return [data[d] for d in recent_dates]
        except:
            return []
