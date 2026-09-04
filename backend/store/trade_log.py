import json
import os
import aiosqlite
from datetime import datetime
from typing import List, Optional
from backend.models.trade import TradeRecord, TradeStatus

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "trades.db")

class TradeLog:
    """SQLite persistence and lifecycle state engine for Trade Records."""
    
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

    async def get_trade_by_id(self, trade_id: str) -> Optional[TradeRecord]:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT data FROM trades WHERE trade_id = ?", (trade_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return TradeRecord.model_validate_json(row[0])
                return None

    async def get_all_trades(self) -> List[TradeRecord]:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT data FROM trades ORDER BY rowid DESC") as cursor:
                rows = await cursor.fetchall()
                return [TradeRecord.model_validate_json(row[0]) for row in rows]

    async def get_open_trades(self) -> List[TradeRecord]:
        """Fetch all active positions (status == OPEN)."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT data FROM trades WHERE status = ? ORDER BY rowid DESC", (TradeStatus.OPEN.value,)) as cursor:
                rows = await cursor.fetchall()
                return [TradeRecord.model_validate_json(row[0]) for row in rows]

    async def get_pending_trades(self) -> List[TradeRecord]:
        """Fetch all resting limit orders awaiting fill (status == PENDING)."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT data FROM trades WHERE status = ? ORDER BY rowid DESC", (TradeStatus.PENDING.value,)) as cursor:
                rows = await cursor.fetchall()
                return [TradeRecord.model_validate_json(row[0]) for row in rows]

    async def get_history_trades(self) -> List[TradeRecord]:
        """Fetch all completed archived trades (status in CLOSED, TAKE_PROFIT, STOPPED_OUT)."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT data FROM trades WHERE status IN (?, ?, ?) ORDER BY rowid DESC",
                (TradeStatus.CLOSED.value, TradeStatus.TAKE_PROFIT.value, TradeStatus.STOPPED_OUT.value)
            ) as cursor:
                rows = await cursor.fetchall()
                return [TradeRecord.model_validate_json(row[0]) for row in rows]

    async def fill_pending_trade(self, trade_id: str, fill_price: float) -> Optional[TradeRecord]:
        """Transitions a resting PENDING limit order into an active OPEN position."""
        trade = await self.get_trade_by_id(trade_id)
        if not trade:
            return None
        
        trade.status = TradeStatus.OPEN
        trade.entry_time = datetime.now().isoformat()
        trade.proposal.breakevens = [round(fill_price, 2)]
        trade.current_price = fill_price
        
        # If no explicit TP/SL price set yet, establish calibrated defaults
        if not trade.take_profit_price:
            trade.take_profit_price = round(fill_price * 1.04, 2)
            trade.proposal.take_profit = trade.take_profit_price
        if not trade.stop_loss_price:
            trade.stop_loss_price = round(fill_price * 0.982, 2)
            trade.proposal.stop_loss = trade.stop_loss_price

        await self.save_trade(trade)
        return trade

    async def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_type: TradeStatus = TradeStatus.CLOSED,
        reason: str = ""
    ) -> Optional[TradeRecord]:
        """Finalizes an OPEN trade, computes realized PnL, archives to History."""
        trade = await self.get_trade_by_id(trade_id)
        if not trade:
            return None

        entry_price = trade.proposal.breakevens[0] if trade.proposal.breakevens else exit_price
        qty = getattr(trade.proposal, "qty", 1.0) or 1.0
        is_long = getattr(trade.proposal, "side", "BUY").upper() == "BUY"

        if is_long:
            pnl = (exit_price - entry_price) * qty
        else:
            pnl = (entry_price - exit_price) * qty

        trade.status = exit_type
        trade.exit_price = round(exit_price, 2)
        trade.exit_time = datetime.now().isoformat()
        trade.realized_pnl = round(pnl, 2)
        if reason:
            trade.proposal.thesis = f"{trade.proposal.thesis} | Closed: {reason}"

        await self.save_trade(trade)
        return trade

    async def cancel_trade(self, trade_id: str) -> Optional[TradeRecord]:
        """Cancels a PENDING limit order."""
        trade = await self.get_trade_by_id(trade_id)
        if not trade:
            return None
        trade.status = TradeStatus.CANCELLED
        trade.exit_time = datetime.now().isoformat()
        await self.save_trade(trade)
        return trade

trade_log = TradeLog()
