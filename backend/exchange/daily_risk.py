"""Durable first-observation equity risk; coverage begins when monitoring starts."""
import math
import sqlite3
from datetime import datetime, timezone

def observe_equity(db_path, identity, equity, day=None):
    if not math.isfinite(equity) or equity <= 0:
        raise ValueError('Verified positive equity required')
    now = datetime.now(timezone.utc).isoformat()
    day = day or now[:10]
    with sqlite3.connect(db_path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS execution_daily_risk (identity TEXT PRIMARY KEY, day TEXT, baseline REAL, worst_pnl REAL, started_at TEXT)')
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT day, baseline, worst_pnl, started_at FROM execution_daily_risk WHERE identity=?',(identity,)).fetchone()
        if row is None or row[0] != day:
            baseline, pnl, started = equity, 0.0, now
        else:
            baseline, pnl, started = row[1], min(row[2], equity-row[1]), row[3]
        db.execute('INSERT OR REPLACE INTO execution_daily_risk VALUES (?,?,?,?,?)',(identity,day,baseline,pnl,started))
    return {'daily_pnl':pnl,'baseline_equity':baseline,'coverage_started_at':started,'coverage':'first verified observation; observed losses retained'}
