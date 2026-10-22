import json
import hashlib
import os
import aiosqlite
from datetime import datetime
from decimal import Decimal
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

    async def find_trade(self, identity, market='spot', symbol=None):
        candidates=[t for t in await self.get_all_trades() if t.market==market
            and (t.trade_id==identity or t.binance_order_id==identity)
            and (symbol is None or t.proposal.symbol==symbol)]
        if len(candidates)>1:
            raise ValueError('Ambiguous order identity; supply market and symbol')
        return candidates[0] if candidates else None

    async def find_exit_intent(self, market: str, client_order_id: str) -> Optional[TradeRecord]:
        """Find the current or completed exit owner without loading the whole ledger."""
        execution_path = '$.exit_executions."' + client_order_id + '"'
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await (await db.execute("""SELECT data FROM trades
                WHERE json_extract(data,'$.market')=? AND
                (json_extract(data,'$.exit_client_order_id')=? OR json_type(data,?) IS NOT NULL)
                LIMIT 2""", (market, client_order_id, execution_path))).fetchall()
        if len(rows) > 1:
            raise ValueError('Ambiguous tracked exit identity; reservation retained')
        return TradeRecord.model_validate_json(rows[0][0]) if rows else None

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
                trades = [TradeRecord.model_validate_json(row[0]) for row in rows]
        pending = await self.get_pending_trades()
        return trades + [t for t in pending if t.proposal.qty > 0]

    async def update_execution(self, trade, result):
        """Atomic cumulative entry reconciliation; a partial cancel remains exposed."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('BEGIN IMMEDIATE')
            row = await (await db.execute('SELECT data FROM trades WHERE trade_id=?',(trade.trade_id,))).fetchone()
            if row:
                trade=TradeRecord.model_validate_json(row[0])
            if result.executed_qty < trade.executed_qty:
                raise ValueError('Execution quantity cannot regress')
            grew=result.executed_qty>trade.executed_qty
            trade.executed_qty=result.executed_qty
            if result.fees_known is True:
                trade.entry_fees=result.fees
                trade.fees_known=True
            elif grew or trade.fees_known is not True:
                trade.fees_known=False if result.fees_known is False or trade.fees_known is not None else None
            trade.base_asset=result.base_asset or trade.base_asset
            trade.requested_qty=result.orig_qty
            trade.binance_order_id=result.order_id
            trade.client_order_id=result.client_order_id or trade.client_order_id
            trade.exchange_status=result.exchange_status
            trade.entry_price=trade.proposal.entry_price=result.entry_price
            trade.proposal.qty=self._held_quantity(trade)
            trade.proposal.breakevens=[result.entry_price] if result.entry_price else []
            trade.current_price=result.current_price
            if result.exchange_status in ('NEW','PENDING_NEW','PARTIALLY_FILLED'):
                trade.status=TradeStatus.PENDING
            elif trade.proposal.qty>0:
                trade.status=TradeStatus.OPEN
            elif trade.closed_qty==0:
                trade.status=TradeStatus.CANCELLED
            await self._write_record(db,trade)
            await db.commit()
            return trade

    @staticmethod
    def _held_quantity(trade):
        """Gross fills remain auditable; only Spot base fees consume inventory."""
        base_fee=Decimal(0)
        if trade.market=='spot':
            base_fee=Decimal(str(trade.entry_fees.get(trade.base_asset,0)))+Decimal(str(trade.exit_fees.get(trade.base_asset,0)))
        return max(0,float(Decimal(str(trade.executed_qty))-Decimal(str(trade.closed_qty))-base_fee))

    async def mark_dust(self, trade_id, reason):
        """Keep untradeable residual inventory visible, never record it as sold."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('BEGIN IMMEDIATE')
            row=await (await db.execute('SELECT data FROM trades WHERE trade_id=?',(trade_id,))).fetchone()
            trade=TradeRecord.model_validate_json(row[0])
            trade.dust_qty=trade.proposal.qty
            trade.dust_reason=reason
            await self._write_record(db,trade)
            await db.commit()
            return trade

    async def prepare_exit(self, trade_id):
        """Atomically choose one durable attempt for all concurrent close callers."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('BEGIN IMMEDIATE')
            row=await (await db.execute('SELECT data FROM trades WHERE trade_id=?',(trade_id,))).fetchone()
            trade=TradeRecord.model_validate_json(row[0])
            if trade.proposal.qty>0 and not trade.exit_client_order_id:
                identity=f'{trade.trade_id}:{trade.closed_qty}:{trade.exit_attempt}'
                trade.exit_client_order_id='vhx-'+hashlib.sha256(identity.encode()).hexdigest()[:32]
                await self._write_record(db,trade)
            await db.commit()
            return trade

    async def save_trade_if_absent(self, record):
        """Initial audit insertion must never replace an existing lifecycle state."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('INSERT OR IGNORE INTO trades VALUES (?,?,?,?,?,?)',
                (record.trade_id,record.status.value,record.proposal.underlying,
                 record.proposal.strategy_type.value,record.realized_pnl,record.model_dump_json()))
            await db.commit()

    async def apply_exit(self, trade_id, result, exit_type=TradeStatus.CLOSED):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('BEGIN IMMEDIATE')
            row=await (await db.execute('SELECT data FROM trades WHERE trade_id=?',(trade_id,))).fetchone()
            trade=TradeRecord.model_validate_json(row[0])
            trade.executed_qty=trade.executed_qty or trade.proposal.qty+trade.closed_qty
            terminal_key=result.client_order_id+':terminal'
            was_terminal=bool(trade.exit_executions.get(terminal_key))
            if was_terminal and not (result.fees_known is True and trade.exit_order_fees.get(result.client_order_id)!=result.fees):
                return trade
            previous=trade.exit_executions.get(result.client_order_id,0)
            delta=result.executed_qty-previous
            if delta<0 or delta>trade.proposal.qty+1e-10:
                raise ValueError('Inconsistent closing execution')
            # Cumulative exit quote is needed when its average price changes.
            quote_key=result.client_order_id+':quote'
            prior_quote=trade.exit_executions.get(quote_key,0)
            quote=result.executed_qty*result.entry_price
            realized=(quote-prior_quote)-trade.entry_price*delta
            trade.realized_pnl=round(trade.realized_pnl+(realized if trade.proposal.side=='BUY' else -realized),8)
            trade.closed_qty=float(Decimal(str(trade.closed_qty))+Decimal(str(result.executed_qty))-Decimal(str(previous)))
            if result.fees_known is True:
                trade.exit_order_fees[result.client_order_id]=result.fees
                trade.exit_order_fees_known[result.client_order_id]=True
            elif delta>0 or result.client_order_id not in trade.exit_order_fees_known:
                trade.exit_order_fees_known[result.client_order_id]=result.fees_known
            trade.exit_fees={}
            for fees in trade.exit_order_fees.values():
                for asset,fee in fees.items():
                    trade.exit_fees[asset]=float(Decimal(str(trade.exit_fees.get(asset,0)))+Decimal(str(fee)))
            known=list(trade.exit_order_fees_known.values())
            trade.exit_fees_known=False if False in known else (True if all(value is True for value in known) else None)
            trade.proposal.qty=self._held_quantity(trade)
            trade.dust_qty=0
            trade.dust_reason=None
            trade.exit_executions[result.client_order_id]=result.executed_qty
            trade.exit_executions[quote_key]=quote
            terminal=result.exchange_status in ('FILLED','CANCELED','EXPIRED','EXPIRED_IN_MATCH','REJECTED')
            if terminal and not was_terminal:
                trade.exit_executions[terminal_key]=1
                trade.exit_attempt+=1
                if trade.exit_client_order_id==result.client_order_id:
                    trade.exit_client_order_id=None
            elif not terminal and trade.exit_client_order_id is None:
                trade.exit_client_order_id=result.client_order_id
            if delta>0:
                trade.exit_price=result.entry_price
            if trade.proposal.qty==0 and result.executed_qty>0:
                trade.status=exit_type
                trade.exit_time=datetime.now().isoformat()
            await self._write_record(db,trade)
            await db.commit()
            return trade

    async def _write_record(self,db,trade):
        await db.execute('INSERT OR REPLACE INTO trades VALUES (?,?,?,?,?,?)',
            (trade.trade_id,trade.status.value,trade.proposal.underlying,trade.proposal.strategy_type.value,trade.realized_pnl,trade.model_dump_json()))

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

    async def fill_pending_trade(self, trade_id, fill_price):
        raise ValueError('An exchange acknowledgement is required; use reconciliation')

    async def close_trade(self, trade_id, exit_price, exit_type=TradeStatus.CLOSED, reason=''):
        raise ValueError('An exchange closing acknowledgement is required')

    async def cancel_trade(self, trade_id):
        raise ValueError('An exchange cancellation acknowledgement is required')

trade_log = TradeLog()
