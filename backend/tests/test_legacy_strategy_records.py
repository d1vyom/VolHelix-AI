import asyncio
import importlib
import json
import sqlite3
from unittest.mock import Mock
import pytest
from backend.models.trade import TradeRecord
from backend.engine.auto_trader import auto_trader

LEGACY=['SPOT_LONG','SPOT_SHORT','DCA_BUY','BREAKOUT_LONG','MEAN_REVERSION','MOMENTUM']

def saved(strategy,status='OPEN'):
    return dict(trade_id=f'{strategy}-{status}',status=status,exchange_status='FILLED',entry_price=100,proposal=dict(id=strategy,symbol='SOLUSDT',strategy_type=strategy,qty=1,entry_price=100))

@pytest.mark.parametrize('strategy',LEGACY)
def test_legacy_strategy_roundtrip_preserves_identity(strategy):
    trade=TradeRecord.model_validate(saved(strategy))
    assert trade.proposal.strategy_type.value==strategy
    assert TradeRecord.model_validate_json(trade.model_dump_json()).proposal.strategy_type.value==strategy

def test_mixed_ledger_history_and_guardian_stay_readable(monkeypatch):
    store=importlib.import_module('backend.store.trade_log')
    rows=[saved(s,status) for s in LEGACY+['MASTER_ORDER_FLOW'] for status in ['OPEN','PENDING','CLOSED']]
    with sqlite3.connect(store.DB_PATH) as db:
        db.executemany('INSERT INTO trades VALUES (?,?,?,?,?,?)',[(r['trade_id'],r['status'],'SOLUSDT',r['proposal']['strategy_type'],0,json.dumps(r)) for r in rows])
    assert len(asyncio.run(store.trade_log.get_all_trades()))==21
    assert len(asyncio.run(store.trade_log.get_history_trades()))==7
    assert len(asyncio.run(store.trade_log.get_open_trades()))==14
    assert len(asyncio.run(store.trade_log.get_pending_trades()))==7
    client=Mock()
    client.get_price.return_value={'price':100}
    monkeypatch.setattr('backend.engine.auto_trader.registry.get_exchange_client',lambda market:client)
    # Pending failures must not stop current OPEN positions being visited.
    auto_trader._check_and_manage_positions()
    assert client.get_price.call_count==14
