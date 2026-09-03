import sys
import os
import asyncio

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.store.trade_log import trade_log
from backend.store.portfolio_store import portfolio_store
from backend.utils.writeup_generator import generate_writeup

async def run_generate():
    print("Generating Hackathon Submission Write-Up (ONE_PAGER.md)...")
    await trade_log.init_db()
    trades = await trade_log.get_all_trades()
    snapshot = portfolio_store.get_snapshot()

    report = generate_writeup(snapshot, trades)
    
    out_path = os.path.join(PROJECT_ROOT, "ONE_PAGER.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
        
    print(f"Write-up generated successfully at {out_path}")

if __name__ == "__main__":
    asyncio.run(run_generate())
