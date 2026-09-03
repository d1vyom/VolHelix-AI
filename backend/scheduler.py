import time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from backend.config import settings
from backend.agents.orchestrator import TradingOrchestrator
from backend.risk.circuit_breaker import CircuitBreaker
from backend.risk.exit_manager import ExitManager
from backend.utils.logger import get_logger

logger = get_logger("scheduler")

class VolHelixScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.orchestrator = TradingOrchestrator()
        self.circuit_breaker = CircuitBreaker()
        self.exit_manager = ExitManager()
        
    def _is_market_open(self) -> bool:
        # Override for testing
        return True
        
    def run_trading_cycle(self):
        logger.info("--- Starting Scheduled Trading Cycle ---")
        
        if not self._is_market_open():
            logger.info("Market is closed. Skipping cycle.")
            return
            
        if self.circuit_breaker.is_halted():
            logger.warning(f"Trading halted due to circuit breaker: {self.circuit_breaker.halt_reason}")
            return
            
        # 1. Manage existing positions (Exits)
        # In a real app, we'd fetch open positions from store/Alpaca
        open_positions = [] 
        current_prices = {} 
        exits = self.exit_manager.check_exits(open_positions, current_prices)
        for trade_id, reason in exits:
            logger.info(f"Executing exit for {trade_id} due to {reason.value}")
            # orchestrator.executor.close_position(...)
            
        # 2. Run Autonomous Agents for new opportunities
        for underlying in settings.WATCHED_UNDERLYINGS:
            try:
                self.orchestrator.run_cycle(underlying)
            except Exception as e:
                logger.error(f"Error in cycle for {underlying}: {e}")
                
    def start(self):
        interval = settings.TRADING_INTERVAL_MINUTES
        self.scheduler.add_job(self.run_trading_cycle, 'interval', minutes=interval)
        self.scheduler.start()
        logger.info(f"Scheduler started. Running every {interval} minutes.")
        
        # Run one immediately for testing
        self.run_trading_cycle()
        
        try:
            # Keep main thread alive if run directly
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self.scheduler.shutdown()
            logger.info("Scheduler shutdown.")

if __name__ == "__main__":
    app = VolHelixScheduler()
    app.start()
