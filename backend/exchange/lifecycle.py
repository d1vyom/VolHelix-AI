"""Narrow market-aware hooks shared by manual, agent, bot and guardian paths."""
import asyncio
import hashlib
from datetime import datetime

from backend.exchange.schemas import OrderRequest
from backend.exchange.execution import submit_order, parse_acknowledgement, OrderExecutionError
from backend.models.trade import TradeRecord, TradeProposal
from backend.models.market import TradeStatus
from backend.store.trade_log import trade_log
from backend.store import order_intents

TERMINAL={'FILLED','CANCELED','REJECTED','EXPIRED','EXPIRED_IN_MATCH'}


def trade_identity(market, symbol, order_id):
    return f'{market}:{symbol}:{order_id}'


def entry_request(trade):
    return OrderRequest(market=trade.market,symbol=trade.proposal.symbol,
        side=trade.proposal.side,order_type=trade.proposal.order_type,
        qty=trade.requested_qty or trade.proposal.qty or .001,
        quote_quantity=trade.proposal.quote_qty,limit_price=trade.proposal.limit_price,
        client_order_id=trade.client_order_id)


async def persist_entry(request, result, *, proposal=None):
    """Upsert cumulative execution without reopening already closed quantities."""
    tid=trade_identity(request.market,request.symbol,result.order_id)
    existing=await trade_log.get_trade_by_id(tid)
    reference=result.entry_price or request.limit_price or result.current_price
    is_long=request.side=='BUY'
    prop=proposal.model_copy(deep=True) if proposal else TradeProposal(
        id=tid,market=request.market,symbol=request.symbol,side=request.side,
        order_type=request.order_type,quote_qty=request.quote_quantity,limit_price=request.limit_price,
        take_profit=reference*(1.04 if is_long else .96),
        stop_loss=reference*(.985 if is_long else 1.015))
    trade=existing or TradeRecord(trade_id=tid,market=request.market,proposal=prop,
        entry_time=datetime.now().isoformat(),take_profit_price=prop.take_profit,
        stop_loss_price=prop.stop_loss)
    return await trade_log.update_execution(trade,result)


async def execute_entry(request, *, client, proposal=None):
    if request.reduce_only or (request.market=='spot' and request.side=='SELL'):
        raise OrderExecutionError('Inventory reductions require the tracked-position close endpoint')
    result=await submit_order(request,client=client)
    trade=await persist_entry(request,result,proposal=proposal)
    return result,trade


async def reconcile_trade(trade, *, client):
    await asyncio.to_thread(order_intents.bind_account,client,trade.market)
    request=entry_request(trade)
    try:
        if trade.client_order_id:
            raw=await asyncio.to_thread(client.get_order_by_client_id,request.symbol,trade.client_order_id)
        else:
            raw=await asyncio.to_thread(client.get_order,request.symbol,trade.binance_order_id)
        result=parse_acknowledgement(raw,request,trade.current_price or trade.entry_price or trade.proposal.limit_price or 1)
        if result.order_id != trade.binance_order_id:
            raise ValueError('Exchange order identity mismatch')
        if trade.client_order_id:
            result=await asyncio.to_thread(order_intents.finish,request,result)
        return await trade_log.update_execution(trade,result)
    except Exception as exc:
        raise OrderExecutionError('Exchange reconciliation unavailable; retained exposure') from exc


async def cancel_trade_order(trade, *, client):
    if trade.exchange_status in TERMINAL:
        return trade
    await asyncio.to_thread(order_intents.bind_account,client,trade.market)
    raw=await asyncio.to_thread(client.cancel_order,trade.proposal.symbol,trade.binance_order_id)
    if raw.get('error'):
        raise OrderExecutionError('Cancellation unavailable; order retained')
    # Query cumulative fills even when a cancel acknowledgement omits fill fields.
    reconciled=await reconcile_trade(trade,client=client)
    if reconciled.exchange_status not in TERMINAL:
        raise OrderExecutionError('Cancellation unconfirmed; order retained')
    return reconciled


async def close_trade_position(trade, *, client, exit_type=TradeStatus.CLOSED):
    trade=await trade_log.get_trade_by_id(trade.trade_id) or trade
    if trade.exchange_status not in TERMINAL:
        trade=await cancel_trade_order(trade,client=client)
        if trade.exchange_status not in TERMINAL:
            raise OrderExecutionError('Entry cancellation unconfirmed; position retained')
    if trade.proposal.qty<=0:
        raise OrderExecutionError('No confirmed exposure to close')
    # Reuse the same durable exit intent until a terminal acknowledgement permits
    # another close for a residual. Concurrent callers select the same client ID.
    client_id=trade.exit_client_order_id or 'vhx-'+hashlib.sha256(f'{trade.trade_id}:{trade.closed_qty}'.encode()).hexdigest()[:32]
    # Persist the original close payload; partial fills change the local residual.
    if trade.exit_client_order_id:
        intent=await asyncio.to_thread(order_intents.lookup,trade.market,client_id)
        if intent:
            request=OrderRequest.model_validate_json(intent['payload'])
            if intent['status'] in TERMINAL:
                result=await submit_order(request,client=client)
            else:
                try:
                    await asyncio.to_thread(order_intents.bind_account,client,trade.market)
                    raw=await asyncio.to_thread(client.get_order_by_client_id,request.symbol,client_id)
                    result=parse_acknowledgement(raw,request,trade.current_price or trade.entry_price)
                    result=await asyncio.to_thread(order_intents.finish,request,result)
                except AttributeError:
                    result=await submit_order(request,client=client)
                except Exception as exc:
                    raise OrderExecutionError('Exit reconciliation unavailable; retained exposure') from exc
            return await trade_log.apply_exit(trade.trade_id,result,exit_type)
    request=OrderRequest(market=trade.market,symbol=trade.proposal.symbol,
        side='SELL' if trade.proposal.side=='BUY' else 'BUY',qty=trade.proposal.qty,
        reduce_only=True,client_order_id=client_id)
    await trade_log.set_exit_intent(trade.trade_id,client_id)
    # Spot closes sell only this recorded exposure, validated against free inventory.
    result=await submit_order(request,client=client)
    return await trade_log.apply_exit(trade.trade_id,result,exit_type)


async def recover_entries():
    """Recover bounded missing-record crash windows without issuing create again."""
    from backend.exchange import registry
    from backend.utils.logger import get_logger
    for intent in await asyncio.to_thread(order_intents.recoverable):
        try:
            request=OrderRequest.model_validate_json(intent['payload'])
            client=await asyncio.to_thread(registry.get_exchange_client,request.market)
            await execute_entry(request,client=client)
        except Exception as exc:
            get_logger('lifecycle').warning(f"Retained {intent['identity']} for reconciliation: {exc}")


async def position_snapshot(market):
    """Keep recorded exposure visible during upstream outages; never infer a close."""
    from backend.exchange import registry
    trades=[t for t in await trade_log.get_open_trades() if t.market==market]
    try:
        client=await asyncio.to_thread(registry.get_exchange_client,market)
        kwargs={'strict':True} if market=='spot' else {}
        live=await asyncio.to_thread(client.get_positions,**kwargs)
        available=True; error=None
    except Exception as exc:
        live=[]; available=False; error=str(exc)
    live_by_symbol={p['symbol']:p for p in live}
    output=[]
    recorded=set()
    for trade in trades:
        symbol=trade.proposal.symbol; recorded.add(symbol)
        live_position=live_by_symbol.get(symbol,{})
        price=live_position.get('current_price')
        if price is None:
            price=trade.current_price or None
        entry=trade.entry_price or trade.proposal.entry_price
        qty=trade.proposal.qty
        direction=1 if trade.proposal.side=='BUY' else -1
        pnl=(float(price)-entry)*qty*direction if price is not None else None
        output.append({'id':trade.trade_id,'trade_id':trade.trade_id,'market':market,
            'symbol':symbol,'qty':qty,'side':'LONG' if direction==1 else 'SHORT',
            'current_price':price,'avg_entry_price':entry,'market_value':abs(float(price)*qty) if price else None,
            'cost_basis':entry*qty,'unrealized_pl':pnl,
            'unrealized_plpc':pnl/(entry*qty)*100 if pnl is not None and entry*qty else None,
            'take_profit_price':trade.take_profit_price,'stop_loss_price':trade.stop_loss_price,
            'strategy':trade.proposal.strategy_type.value,'order_type':trade.proposal.order_type,
            'exchange_status':trade.exchange_status,'stale':not available or not live_position})
    for live_position in live:
        if live_position['symbol'] not in recorded:
            signed=float(live_position['qty'])
            output.append({**live_position,'id':f"{market}:{live_position['symbol']}:wallet",'market':market,
                'side':'LONG' if signed>0 else 'SHORT','qty':abs(signed),
                'avg_entry_price':live_position.get('entry_price'),'take_profit_price':None,
                'stop_loss_price':None,'stale':False})
    return {'market':market,'testnet':True,'positions':output,'available':available,'error':error}


async def order_snapshot(market):
    """Acknowledged and unknown intents remain inspectable after process restart."""
    import json
    trades=[t for t in await trade_log.get_all_trades() if t.market==market]
    output=[{'id':t.trade_id,'trade_id':t.trade_id,'order_id':t.binance_order_id,
        'client_order_id':t.client_order_id,'market':market,'symbol':t.proposal.symbol,
        'side':t.proposal.side,'type':t.proposal.order_type,'qty':t.requested_qty,
        'executed_qty':t.executed_qty,'status':t.exchange_status or t.status.value,
        'filled_avg_price':t.entry_price or None,'limit_price':t.proposal.limit_price,
        'created_at':t.entry_time,'order_class':market.upper()} for t in trades]
    seen={t.client_order_id for t in trades}
    for row in await asyncio.to_thread(order_intents.pending,market):
        req=json.loads(row['payload'])
        if req['client_order_id'] not in seen:
            result=json.loads(row['result']) if row['result'] else {}
            output.append({'id':row['identity'],'client_order_id':req['client_order_id'],
                'market':market,'symbol':req['symbol'],'side':req['side'],'type':req['order_type'],
                'qty':row['quantity'],'executed_qty':result.get('executed_qty',0),
                'status':row['status'],'reduce_only':req['reduce_only'],'limit_price':req['limit_price']})
    return output
