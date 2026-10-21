"""Durable dispatch claims and reservations in the existing trade SQLite store."""
import json
import sqlite3
import time
from importlib import import_module
from contextlib import contextmanager
import hashlib


@contextmanager
def connect():
    db = sqlite3.connect(import_module('backend.store.trade_log').DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('''CREATE TABLE IF NOT EXISTS order_intents (
        identity TEXT PRIMARY KEY, market TEXT, symbol TEXT, payload TEXT,
        status TEXT, notional REAL, quantity REAL, updated REAL, result TEXT)''')
    try:
        with db:
            yield db
    finally:
        db.close()


def bind_account(client,market,create=True):
    """This ledger is pinned to one testnet account per market; fail on key changes."""
    from backend.config import settings
    key=getattr(getattr(client,'trading_client',None),'API_KEY',None)
    if not isinstance(key,str):
        key=settings.BINANCE_FUTURES_API_KEY if market=='futures' else settings.BINANCE_API_KEY
    digest=hashlib.sha256((market+'-testnet:'+key).encode()).hexdigest()
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS execution_accounts (market TEXT PRIMARY KEY, digest TEXT)')
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT digest FROM execution_accounts WHERE market=?',(market,)).fetchone()
        if old and old['digest']!=digest:
            raise ValueError('Execution account identity mismatch; use the original testnet account or a separate ledger')
        if create:
            db.execute('INSERT OR IGNORE INTO execution_accounts VALUES (?,?)',(market,digest))


def identity(request):
    return f'{request.market}:{request.client_order_id}'


def lookup(market,client_id):
    with connect() as db:
        row=db.execute('SELECT * FROM order_intents WHERE identity=?',(f'{market}:{client_id}',)).fetchone()
        return dict(row) if row else None


def get(request):
    with connect() as db:
        row = db.execute('SELECT * FROM order_intents WHERE identity=?',(identity(request),)).fetchone()
        if not row:
            return None
        if row['payload'] != request.model_dump_json():
            raise ValueError('Client order ID payload conflict')
        return dict(row)


def claim(request, verdict, account, snapshot_started):
    """Serialize reserve/check/insert; never call the exchange inside this transaction."""
    from backend.risk.risk_gate import CryptoRiskGate as Gate
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM order_intents WHERE identity=?',(identity(request),)).fetchone()
        if row:
            if row['payload'] != request.model_dump_json():
                raise ValueError('Client order ID payload conflict')
            return dict(row)
        rows = db.execute("SELECT * FROM order_intents WHERE market=? AND (status NOT IN ('FILLED','CANCELED','REJECTED','EXPIRED','EXPIRED_IN_MATCH') OR updated>=?)", (request.market,snapshot_started)).fetchall()
        active = []
        for row in rows:
            payload=json.loads(row['payload'])
            result=json.loads(row['result']) if row['result'] else {}
            if row['status'] in ('REJECTED','CANCELED','EXPIRED','EXPIRED_IN_MATCH','FILLED'):
                # A concurrent snapshot may predate a confirmed fill.
                remaining = float(result.get('executed_qty',0)) if row['updated'] >= snapshot_started else 0
            else:
                remaining = row['quantity']
            if remaining:
                active.append((row,payload,remaining))
        quantity=float(verdict['quantity']); value=float(verdict['notional'])
        inventory_reserved=sum(q for row,p,q in active if row['symbol']==request.symbol and p['side']==request.side)
        balances=account.get('balances',{})
        if request.market=='spot':
            base=request.symbol.removesuffix('USDT')
            if request.side=='SELL' and quantity+inventory_reserved > float(balances.get(base,{}).get('free',0)):
                raise ValueError('Inventory reservation exceeds available quantity')
        if request.reduce_only:
            if request.market=='futures':
                signed=sum(float(p['qty']) for p in account.get('positions',[]) if p['symbol']==request.symbol)
                if quantity+inventory_reserved>abs(signed):
                    raise ValueError('Exit reservation exceeds position')
        else:
            exposure={}
            if request.market=='futures':
                exposure={p['symbol']:float(p['market_value']) for p in account.get('positions',[]) if float(p['qty'])!=0}
            else:
                exposure={a+'USDT':float(b.get('value_usdt',0)) for a,b in balances.items() if a!='USDT' and float(b.get('total',0))>0}
            pending_funds=0
            for row,p,q in active:
                if p['reduce_only']:
                    continue
                amount=row['notional']*q/row['quantity']
                exposure[row['symbol']]=exposure.get(row['symbol'],0)+amount
                if request.market=='futures' or p['side']=='BUY': pending_funds+=amount
            nav=float(account['equity'])
            if (request.market=='futures' or request.side=='BUY') and value+pending_funds>float(account['buying_power']):
                raise ValueError('Funds reservation exceeds available balance')
            if sum(exposure.values())+value>Gate.MAX_EXPOSURE_PCT*nav:
                raise ValueError('Portfolio exposure reservation exceeds limit')
            if exposure.get(request.symbol,0)+value>Gate.MAX_SINGLE_ASSET_PCT*nav:
                raise ValueError('Single asset reservation exceeds limit')
            if request.symbol not in exposure and len(exposure)>=Gate.MAX_POSITIONS:
                raise ValueError('Position reservation exceeds limit')
            if any(request.symbol in group and request.symbol not in exposure and sum(s in exposure for s in group)>=2 for group in Gate.CORRELATION_GROUPS.values()):
                raise ValueError('Correlation reservation exceeds limit')
        db.execute('INSERT INTO order_intents VALUES (?,?,?,?,?,?,?,?,?)',
                   (identity(request),request.market,request.symbol,request.model_dump_json(),'DISPATCHING',value,quantity,time.time(),None))
        return None


def finish(request, result=None, status='UNKNOWN'):
    from backend.exchange.schemas import OrderResult
    terminal={'FILLED','CANCELED','REJECTED','EXPIRED','EXPIRED_IN_MATCH'}
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if result:
            old=db.execute('SELECT status,result FROM order_intents WHERE identity=?',(identity(request),)).fetchone()
            if old and old['result']:
                previous=OrderResult.model_validate_json(old['result'])
                if previous.order_id!=result.order_id:
                    raise ValueError('Exchange order identity changed')
                if previous.executed_qty>result.executed_qty or (previous.exchange_status in terminal and result.exchange_status not in terminal):
                    return previous
            db.execute('UPDATE order_intents SET status=?, result=?, updated=? WHERE identity=?',
                       (result.exchange_status,result.model_dump_json(),time.time(),identity(request)))
            return result
        db.execute("UPDATE order_intents SET status=?, updated=? WHERE identity=? AND status IN ('DISPATCHING','UNKNOWN')",
                   (status,time.time(),identity(request)))


def recoverable():
    with connect() as db:
        rows=db.execute("""SELECT * FROM order_intents AS intent
            WHERE json_extract(payload,'$.reduce_only')=0
            AND status!='REJECTED'
            AND NOT EXISTS (SELECT 1 FROM trades WHERE
                json_extract(data,'$.market')=intent.market
                AND json_extract(data,'$.client_order_id')=json_extract(intent.payload,'$.client_order_id'))
            ORDER BY updated LIMIT 100""").fetchall()
        return [dict(row) for row in rows]


def pending(market=None):
    with connect() as db:
        rows=db.execute("SELECT * FROM order_intents WHERE status NOT IN ('FILLED','CANCELED','REJECTED','EXPIRED','EXPIRED_IN_MATCH')").fetchall()
        return [dict(row) for row in rows if market is None or row['market']==market]
