import random
from backend.models.market import Regime, MarketSignal

class RegimeEngine:
    """Simple regime classifier.
    In a full implementation this would be an HMM trained on historical IV data.
    For now we use a heuristic based on the IV percentile.
    """
    def classify(self, signal: MarketSignal) -> Regime:
        # Heuristic mapping of iv_percentile to regime
        p = signal.iv_percentile
        if p >= 0.8:
            return Regime.CRISIS
        if p >= 0.6:
            return Regime.ELEVATED
        if p >= 0.4:
            return Regime.SQUEEZE
        if p >= 0.2:
            return Regime.NORMAL
        return Regime.LOW_VOL
