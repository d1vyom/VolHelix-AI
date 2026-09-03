from datetime import datetime
from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger("circuit_breaker")

class CircuitBreaker:
    def __init__(self):
        self.max_drawdown = settings.MAX_DAILY_DRAWDOWN
        self.halted = False
        self.halt_reason = ""
        self.halt_time = None
        
    def is_halted(self) -> bool:
        return self.halted
        
    def check_drawdown(self, daily_pnl: float, nav: float) -> bool:
        """
        Check if daily loss exceeds the maximum allowed drawdown.
        daily_pnl should be negative for a loss.
        """
        if daily_pnl >= 0:
            return False
            
        drawdown_pct = abs(daily_pnl) / nav
        if drawdown_pct >= self.max_drawdown:
            self.halt_trading(f"Daily drawdown {drawdown_pct*100:.2f}% exceeded limit {self.max_drawdown*100:.2f}%")
            return True
            
        return False
        
    def halt_trading(self, reason: str):
        if not self.halted:
            self.halted = True
            self.halt_reason = reason
            self.halt_time = datetime.now()
            logger.error(f"CIRCUIT BREAKER TRIGGERED: {reason}")
            
    def reset(self):
        if self.halted:
            logger.info("Circuit breaker reset for new trading day.")
            self.halted = False
            self.halt_reason = ""
            self.halt_time = None
