"""Nonblocking market-aware testnet dispatch and acknowledgement validation."""
import asyncio
import math
import uuid
from decimal import Decimal
from backend.exchange.schemas import OrderRequest, OrderResult

class OrderExecutionError(Exception):
    """Exchange failed or returned an unusable acknowledgement."""
    outcome = 'UNKNOWN'

class OrderNotDispatched(OrderExecutionError):
    """A pre-dispatch check failed; no create call was made for this request."""
    outcome = 'NOT_DISPATCHED'

class OrderRejected(OrderExecutionError):
    """The exchange acknowledgement durably proves a rejection."""
    outcome = 'REJECTED'

class OrderOutcomeUnknown(OrderExecutionError):
    """The original execution cannot be resolved; retain its client order ID."""

class MarketDataUnavailable(OrderNotDispatched):
    """A finite positive production quote could not be obtained."""

def execution_error_detail(exc: OrderExecutionError, market: str, client_order_id: str | None = None) -> dict:
    """Expose proven outcomes independently of HTTP status or human wording."""
    return {'outcome':exc.outcome, 'message':str(exc), 'market':market, 'client_order_id':client_order_id}

def validate_order(request, *, client):
    """Fresh server inputs only. Preview verdicts never authorize dispatch."""
    if request.market == 'futures':
        from backend.exchange.futures_risk import validate_futures_order
        return validate_futures_order(request,client=client)
    from backend.models.trade import TradeProposal
    from backend.models.portfolio import PortfolioSnapshot
    from backend.risk.risk_gate import CryptoRiskGate
    checks = {}
    try:
        price = Decimal(str(client.get_price(request.symbol)['price']))
        if not price.is_finite() or price <= 0:
            raise ValueError('Market price unavailable')
        info = client.get_execution_info(request.symbol)
        if info.get('error') or info.get('status') != 'TRADING':
            raise ValueError('Exchange symbol unavailable')
        context = {} if request.reduce_only else client.get_execution_context(request.symbol)
        account = client.get_account() if request.reduce_only else context['account']
        if account.get('error') or account.get('can_trade') is False:
            raise ValueError('Account unavailable')
        balances = account.get('balances', {})
        quantity = Decimal(str(request.qty))
        notional_price = Decimal(str(request.limit_price)) if request.order_type == 'LIMIT' else price
        notional = Decimal(str(request.quote_quantity)) if request.quote_quantity else quantity * notional_price
        if request.quote_quantity:
            quantity = notional / price
        free_base = Decimal(str(balances.get(info['base_asset'], {}).get('free', 0)))
        checks['entry_side'] = request.reduce_only or request.side=='BUY'
        checks['inventory'] = request.side != 'SELL' or (not request.quote_quantity and quantity <= free_base)
        checks['reduce_only'] = not request.reduce_only or (request.side == 'SELL' and not request.quote_quantity and quantity <= free_base)
        checks['funds'] = request.side != 'BUY' or notional <= Decimal(str(account.get('buying_power', 0)))
        checks['exchange_filters'] = passes_exchange_filters(request,info,quantity,notional_price,notional)
        if not request.reduce_only:
            nav = float(account.get('equity', 0))
            pnl = account.get('daily_pnl')
            checks['account_risk_known'] = math.isfinite(nav) and nav > 0 and pnl is not None and math.isfinite(float(pnl))
            score = float(context.get('score', 0))
            checks['confluence'] = math.isfinite(score) and score >= .70 and context.get('is_valid') is True and context.get('side') == request.side
            baseline = float(account.get('baseline_equity', nav))
            checks['observed_drawdown'] = checks['account_risk_known'] and math.isfinite(baseline) and baseline > 0 and max(0, -float(pnl)) / min(nav, baseline) < CryptoRiskGate.MAX_DAILY_DRAWDOWN
            if checks['account_risk_known']:
                snapshot = PortfolioSnapshot(equity=nav,buying_power=account.get('buying_power',0),daily_pnl=min(float(pnl),0),balances={asset:dict(data, asset=asset) for asset,data in balances.items()})
                proposal = TradeProposal(id='execution-risk',symbol=request.symbol,side=request.side,qty=float(quantity),entry_price=float(notional_price),stop_loss=context.get('stop_loss'),take_profit=context.get('take_profit'))
                verdict = CryptoRiskGate().evaluate(proposal,snapshot)
                checks.update({k:v.passed for k,v in verdict.checks.items()})
        approved = all(checks.values())
        return {'approved':approved,'checks':checks,'reason':'Approved' if approved else 'Failed: '+', '.join(k for k,v in checks.items() if not v),'symbol':request.symbol,'side':request.side,'quantity':str(quantity),'price':str(notional_price),'market_price':str(price),'notional':str(notional),'market':'spot','order_type':request.order_type,'testnet':True,'reduce_only':request.reduce_only,'risk_coverage':account.get('coverage'),'coverage_started_at':account.get('coverage_started_at'),'_reservation_account':account}
    except Exception as exc:
        return {'approved':False,'checks':checks,'reason':str(exc)}

def passes_exchange_filters(request, info, quantity, price, notional):
    """Exact decimal testnet rules, shared without sharing Spot inventory policy."""
    filters = info.get('filters', [])
    if not filters:
        return False
    for f in filters:
        kind = f['filterType']
        if kind in ('LOT_SIZE', 'MARKET_LOT_SIZE') and (kind != 'MARKET_LOT_SIZE' or request.order_type == 'MARKET'):
            for key, passes in [('minQty',lambda n:quantity>=n),('maxQty',lambda n:quantity<=n),
                                ('stepSize',lambda n:request.quote_quantity is not None or quantity%n==0)]:
                value = Decimal(str(f.get(key,0)))
                if value > 0 and not passes(value): return False
        if kind in ('MIN_NOTIONAL','NOTIONAL'):
            # Futures exempts reduce-only orders from min-notional, enabling dust exits.
            if not (request.market == 'futures' and request.reduce_only):
                if notional < Decimal(str(f.get('minNotional',f.get('notional',0)))): return False
            maximum = Decimal(str(f.get('maxNotional',0)))
            if maximum > 0 and notional > maximum: return False
        if kind == 'PRICE_FILTER' and request.order_type == 'LIMIT':
            tick = Decimal(str(f.get('tickSize',0)))
            minimum = Decimal(str(f.get('minPrice',0)))
            maximum = Decimal(str(f.get('maxPrice',0)))
            if (tick > 0 and price%tick != 0) or price < minimum or (maximum > 0 and price > maximum): return False
    return True

async def preview_order(request: OrderRequest, *, client):
    verdict=await asyncio.to_thread(validate_order, request, client=client)
    verdict.pop('_reservation_account',None)
    return verdict

def parse_acknowledgement(response, request, current_price):
    """Validate cumulative exchange amounts, including terminal partial fills."""
    if response.get('error') or not response.get('order_id'):
        raise ValueError('Exchange rejected or did not acknowledge order')
    for field,expected in [('symbol',request.symbol),('side',request.side),('client_order_id',request.client_order_id)]:
        if response.get(field) is not None and response[field]!=expected:
            raise ValueError('Exchange acknowledgement identity mismatch')
    executed = Decimal(str(response.get('executed_qty', 0)))
    original = Decimal(str(response.get('orig_qty', 0)))
    quote_qty = Decimal(str(response.get('cummulative_quote_qty', 0)))
    if not all(value.is_finite() for value in (executed, original, quote_qty)):
        raise ValueError('Nonfinite execution amounts')
    if original <= 0 or executed < 0 or executed > original or quote_qty < 0:
        raise ValueError('Inconsistent executed/original quantities')
    if request.quote_quantity is None and original != Decimal(str(request.qty)):
        raise ValueError('Exchange acknowledged a different requested quantity')
    status = response['status']
    if status in ('NEW', 'PENDING_NEW') and executed != 0:
        raise ValueError('Unfilled status has executed quantity')
    if status == 'PARTIALLY_FILLED' and not 0 < executed < original:
        raise ValueError('Partial status requires partial execution')
    if status == 'FILLED' and executed != original:
        raise ValueError('Filled status must match original quantity')
    if executed == 0 and quote_qty != 0:
        raise ValueError('Unfilled order has executed quote amount')
    fills = response.get('fills', [])
    if executed > 0 and quote_qty == 0 and fills:
        filled_qty = Decimal(0)
        for fill in fills:
            quantity = Decimal(str(fill['qty']))
            fill_price = Decimal(str(fill['price']))
            if not quantity.is_finite() or not fill_price.is_finite() or quantity <= 0 or fill_price <= 0:
                raise ValueError('Invalid fill quantity or price')
            filled_qty += quantity
            quote_qty += quantity * fill_price
        if filled_qty != executed:
            raise ValueError('Fill list does not cover executed quantity')
    price = quote_qty / executed if executed > 0 else 0
    result = OrderResult(order_id=str(response['order_id']), client_order_id=request.client_order_id, exchange_status=response['status'],
                         executed_qty=executed, orig_qty=response.get('orig_qty', 0),
                         entry_price=price, current_price=current_price)
    if (executed > 0 and price <= 0) or (result.exchange_status == 'FILLED' and executed <= 0):
        raise ValueError('Filled acknowledgement lacks actual execution')
    return result

async def submit_order(request: OrderRequest, *, client) -> OrderResult:
    """Persist intent before dispatch; retries reconcile instead of creating twice."""
    import time
    from backend.store import order_intents
    request=request.model_copy(update={'client_order_id':request.client_order_id or 'vh-'+uuid.uuid4().hex})
    try:
        await asyncio.to_thread(order_intents.bind_account,client,request.market,False)
        existing=await asyncio.to_thread(order_intents.get,request)
    except ValueError as exc:
        # Until both checks succeed, a prior dispatch under this ID is unresolved.
        raise OrderOutcomeUnknown(str(exc)) from exc
    if existing:
        return await _reuse_intent(request,existing,client)
    try:
        quote = await asyncio.to_thread(client.get_price, request.symbol)
        current_price = float(quote.get('price', 0))
        if not math.isfinite(current_price) or current_price <= 0:
            raise ValueError('Invalid quote')
    except Exception as exc:
        raise MarketDataUnavailable('Market price unavailable') from exc
    snapshot_started=time.time()
    verdict = await asyncio.to_thread(validate_order, request, client=client)
    if not verdict['approved']:
        raise OrderNotDispatched(verdict['reason'])
    try:
        await asyncio.to_thread(order_intents.bind_account,client,request.market)
        account=verdict['_reservation_account']
        existing=await asyncio.to_thread(order_intents.claim,request,verdict,account,snapshot_started)
    except (ValueError,KeyError,TypeError) as exc:
        raise OrderNotDispatched(str(exc)) from exc
    if existing:
        return await _reuse_intent(request,existing,client)
    kwargs = dict(symbol=request.symbol, side=request.side, order_type=request.order_type,
                  client_order_id=request.client_order_id, reduce_only=request.reduce_only)
    if request.quote_quantity is not None:
        kwargs['quote_quantity'] = request.quote_quantity
    else:
        kwargs['quantity'] = request.qty
    if request.order_type == 'LIMIT':
        kwargs['price'] = request.limit_price
    try:
        try:
            response = await asyncio.to_thread(client.place_order, **kwargs)
            if response.get('status') == 'UNKNOWN':
                raise TimeoutError('Uncertain submission')
        except OrderOutcomeUnknown:
            raise
        except Exception:
            response = await asyncio.to_thread(client.get_order_by_client_id, request.symbol, request.client_order_id)
        result=parse_acknowledgement(response,request,current_price)
        result=await asyncio.to_thread(order_intents.finish,request,result)
    except Exception as exc:
        await asyncio.to_thread(order_intents.finish,request)
        raise OrderOutcomeUnknown(f'Order outcome unavailable; reconcile client ID {request.client_order_id} before retrying') from exc
    if result.exchange_status=='REJECTED':
        raise OrderRejected('Exchange rejected order')
    return result


async def _reuse_intent(request, existing, client):
    from backend.store import order_intents
    if existing['result'] and existing['status']!='UNKNOWN':
        result=OrderResult.model_validate_json(existing['result'])
        if result.exchange_status=='REJECTED':
            raise OrderRejected('Exchange rejected order')
        return result
    try:
        response=await asyncio.to_thread(client.get_order_by_client_id,request.symbol,request.client_order_id)
        # Reconciliation relies on executed amounts, never on a fresh market quote.
        result=parse_acknowledgement(response,request,float(existing['notional'])/float(existing['quantity']))
        result=await asyncio.to_thread(order_intents.finish,request,result)
        if result.exchange_status=='REJECTED':
            raise OrderRejected('Exchange rejected order')
        return result
    except OrderExecutionError:
        raise
    except Exception as exc:
        raise OrderOutcomeUnknown(f'UNKNOWN order outcome; reconcile client ID {request.client_order_id}') from exc
