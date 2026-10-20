"""Nonblocking Spot testnet dispatch and acknowledgement validation."""
import asyncio
import math
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
        executed = float(response.get('executed_qty', 0))
        quote_qty = float(response.get('cummulative_quote_qty', 0))
        fills = response.get('fills', [])
        if executed > 0 and quote_qty == 0 and fills:
            quote_qty = sum(float(fill['price']) * float(fill['qty']) for fill in fills)
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
