import asyncio
import json
import os
import sys
from backend.marketdata.hub import MarketDataHub
from backend.marketdata.models import Trade, StreamHealth
from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger("flow_replay")

async def run_replay():
    logger.info("Starting Flow Replay Mode...")
    
    # Enforce safety - Replay data must not trigger live trades
    settings.FLOW_CONFLUENCE_ENABLED = False 
    
    fixture_path = os.path.join("backend", "tests", "fixtures", "aggtrades_btcusdt.json")
    if not os.path.exists(fixture_path):
        logger.error(f"Replay fixture not found at {fixture_path}")
        sys.exit(1)
        
    with open(fixture_path, "r") as f:
        try:
            trades_data = json.load(f)
        except json.JSONDecodeError:
            logger.error("Failed to parse fixture JSON")
            sys.exit(1)
            
    hub = MarketDataHub()
    # Note: We do not call hub.start() because that would connect to Binance.
    # We will manually inject data into the hub's state.
    
    # Initialize basic health state for UI to show REPLAY
    health = StreamHealth(
        symbol="BTCUSDT",
        connected=True,
        streams=["REPLAY_MODE"],
        last_trade_ts=0,
        last_book_ts=0,
        messages_per_sec=10.0,
        reconnects=0,
        book_resyncs=0,
        gap_events=0,
        lag_ms=0,
        status="LIVE" 
    )
    hub._health["BTCUSDT"] = health
    
    logger.info(f"Loaded {len(trades_data)} trades for replay. Injecting...")
    
    for trade_dict in trades_data:
        trade = Trade(
            symbol=trade_dict.get("s", "BTCUSDT"),
            agg_id=trade_dict.get("a", 0),
            price=float(trade_dict.get("p", 0.0)),
            qty=float(trade_dict.get("q", 0.0)),
            quote_qty=float(trade_dict.get("p", 0.0)) * float(trade_dict.get("q", 0.0)),
            ts=trade_dict.get("T", 0),
            is_buyer_maker=trade_dict.get("m", False),
            side="SELL" if trade_dict.get("m", False) else "BUY",
            first_id=trade_dict.get("f", 0),
            last_id=trade_dict.get("l", 0)
        )
        await hub._process_trade(trade)
        await asyncio.sleep(0.01) # Simulate pacing
        
    logger.info("Replay completed.")

if __name__ == "__main__":
    asyncio.run(run_replay())
