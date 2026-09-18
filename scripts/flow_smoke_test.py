import asyncio
import sys
import time
from backend.marketdata.hub import MarketDataHub
from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger("smoke_test")

async def run_smoke_test():
    logger.info("Starting Flow Smoke Test for 60 seconds...")
    settings.FLOW_ENABLED = True
    hub = MarketDataHub()
    
    await hub.start()
    
    start_time = time.time()
    success = False
    
    try:
        while time.time() - start_time < 60:
            health = hub.get_health("BTCUSDT")
            metrics = hub.get_metrics("BTCUSDT")
            
            if health and health.status == "LIVE" and metrics:
                logger.info(f"LIVE: BTCUSDT | Spread: {metrics.spread:.2f} | Bar Delta: {metrics.bar_delta:.2f} | CVD: {metrics.session_cvd:.2f}")
                success = True
            elif health:
                logger.info(f"Health status: {health.status}")
            else:
                logger.info("Waiting for data...")
                
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        pass
    finally:
        await hub.stop()
        
    if success:
        logger.info("Smoke test passed: Data received successfully.")
        sys.exit(0)
    else:
        logger.error("Smoke test failed: Did not receive LIVE status and metrics.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_smoke_test())
