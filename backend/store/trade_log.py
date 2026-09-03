import json
import os
import aiosqlite
from typing import List, Optional
from backend.models.trade import TradeRecord, TradeStatus

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "trades.db")

class TradeLog:
    """SQLite persistence for Trade Records."""
    
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
    async def init_db(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id TEXT PRIMARY KEY,
                    status TEXT,
                    underlying TEXT,
                    strategy_type TEXT,
                    realized_pnl REAL,
                    data JSON
                )
            """)
            await db.commit()

    async def save_trade(self, record: TradeRecord):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO trades (trade_id, status, underlying, strategy_type, realized_pnl, data)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.trade_id, 
                    record.status.value, 
                    record.proposal.underlying, 
                    record.proposal.strategy_type.value,
                    record.realized_pnl,
                    record.model_dump_json()
                )
            )
            await db.commit()

    async def get_all_trades(self) -> List[TradeRecord]:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT data FROM trades ORDER BY rowid DESC") as cursor:
                rows = await cursor.fetchall()
                return [TradeRecord.model_validate_json(row[0]) for row in rows]

    async def get_open_trades(self) -> List[TradeRecord]:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT data FROM trades WHERE status = ?", (TradeStatus.OPEN.value,)) as cursor:
                rows = await cursor.fetchall()
                return [TradeRecord.model_validate_json(row[0]) for row in rows]

trade_log = TradeLog()
