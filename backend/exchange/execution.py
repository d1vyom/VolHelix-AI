"""Nonblocking Spot testnet dispatch and acknowledgement validation."""
import asyncio
import math
from decimal import Decimal
from backend.exchange.schemas import OrderRequest, OrderResult

class OrderExecutionError(Exception):
    """Exchange failed or returned an unusable acknowledgement."""

class MarketDataUnavailable(OrderExecutionError):
    """A finite positive production quote could not be obtained."""

async def submit_order(request: OrderRequest, *, client) -> OrderResult:
    """Dispatch once, preserving failures and actual executed base quantity."""
    try:
        quote = await asyncio.to_thread(client.get_price, request.symbol)
        current_price = float(quote.get('price', 0))
        if not math.isfinite(current_price) or current_price <= 0:
            raise ValueError('Invalid quote')
    except Exception as exc:
        raise MarketDataUnavailable('Market price unavailable') from exc
    kwargs = dict(symbol=request.symbol, side=request.side, order_type=request.order_type)
    if request.quote_quantity is not None:
        kwargs['quote_quantity'] = request.quote_quantity
    else:
        kwargs['quantity'] = request.qty
    if request.order_type == 'LIMIT':
        kwargs['price'] = request.limit_price
    try:
        response = await asyncio.to_thread(client.place_order, **kwargs)
        if response.get('error') or not response.get('order_id'):
            raise ValueError('Exchange rejected or did not acknowledge order')
        executed = Decimal(str(response.get('executed_qty', 0)))
        original = Decimal(str(response.get('orig_qty', 0)))
        quote_qty = Decimal(str(response.get('cummulative_quote_qty', 0)))
        if not all(value.is_finite() for value in (executed, original, quote_qty)):
            raise ValueError('Nonfinite execution amounts')
        if original <= 0 or executed < 0 or executed > original or quote_qty < 0:
            raise ValueError('Inconsistent executed/original quantities')
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
        result = OrderResult(order_id=str(response['order_id']), exchange_status=response['status'],
                             executed_qty=executed, orig_qty=response.get('orig_qty', 0),
                             entry_price=price, current_price=current_price)
        if (executed > 0 and price <= 0) or (result.exchange_status == 'FILLED' and executed <= 0):
            raise ValueError('Filled acknowledgement lacks actual execution')
        return result
    except Exception as exc:
        # Do not retry uncertain submissions: reconciliation must establish outcome.
        raise OrderExecutionError('Order failed or acknowledgement unavailable; reconcile before retrying') from exc
