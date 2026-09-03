import json
import os
from datetime import datetime
from backend.models.market import Regime

REGIME_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "regime_log.jsonl")

def save_regime(regime: Regime, vix: float, iv_percentile: float):
    """Track regime transitions over time."""
    os.makedirs(os.path.dirname(REGIME_LOG_PATH), exist_ok=True)
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "regime": regime.value,
        "vix": vix,
        "iv_percentile": iv_percentile
    }
    
    with open(REGIME_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

def get_regime_history(limit: int = 100) -> list:
    """Retrieve recent regime history."""
    if not os.path.exists(REGIME_LOG_PATH):
        return []
        
    history = []
    with open(REGIME_LOG_PATH, "r") as f:
        for line in f:
            try:
                history.append(json.loads(line.strip()))
            except:
                pass
                
    return history[-limit:]
