import sys
import os
import asyncio
import random
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.store.iv_history import iv_history


async def seed_data():
    print("Seeding IV History database for initial percentiles...")
    await iv_history.init_db()
    
    symbols = ["SPY", "QQQ", "AAPL", "NVDA", "TSLA"]
    now = datetime.now()
    
    for symbol in symbols:
        print(f"Generating synthetic 30-day IV history for {symbol}...")
        for i in range(30, 0, -1):
            date_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            
            # Base IV depends on the symbol
            base_iv = {"SPY": 0.12, "QQQ": 0.16, "AAPL": 0.18, "NVDA": 0.45, "TSLA": 0.50}[symbol]
            
            # Add random walk noise
            noise = random.uniform(-0.02, 0.02)
            historical_iv = max(0.05, base_iv + noise)
            
            await iv_history.record_iv(symbol, historical_iv)
            
    print("[OK] Database seeded with 30-day historical IV data.")
    print("This allows the IV Percentile (IV Rank) calculator to work on day 1.")

if __name__ == "__main__":
    asyncio.run(seed_data())
