"""Deterministic offline schedules for durable tracked-close identity ownership."""
import asyncio
from unittest.mock import Mock

import pytest

from backend.exchange import lifecycle
from backend.exchange.lifecycle import close_trade_position
from backend.exchange.execution import OrderNotDispatched, OrderOutcomeUnknown, submit_order
from backend.exchange.schemas import OrderRequest
from backend.store.trade_log import trade_log
from backend.tests.test_execution_risk import Client
from backend.tests.test_market_lifecycle import record, ack


def client():
    c = Client()
    c.account['balances']['SOL'] = {'free': 2, 'total': 2, 'value_usdt': 200}
    return c


@pytest.mark.parametrize('supplied', [True, False])
def test_inflight_attempt_keeps_identity_after_other_caller_terminal_partial(monkeypatch, supplied):
    async def scenario():
        t = record(); t.fees_known = True
        await trade_log.save_trade(t)
        c = client()
        c.place_order = Mock(side_effect=lambda **kw: ack('CANCELED', kw['quantity'], .4, oid='exit'))
        original = trade_log.prepare_exit
        ready, release = asyncio.Event(), asyncio.Event()
        selected = []

        async def controlled(trade_id, **kwargs):
            prepared = await original(trade_id, **kwargs)
            if asyncio.current_task().get_name() == 'paused-close' and not selected:
                selected.append(prepared.exit_client_order_id)
                ready.set()
                await release.wait()
            return prepared

        monkeypatch.setattr(trade_log, 'prepare_exit', controlled)
        a = asyncio.create_task(close_trade_position(t, client=c,
            client_order_id='confirmed-close' if supplied else None), name='paused-close')
        await asyncio.wait_for(ready.wait(), 5)
        try:
            b = await close_trade_position(t, client=c, client_order_id=selected[0])
            assert b.proposal.qty == .6
        finally:
            release.set()
        result = await a
        assert c.place_order.call_count == 1
        assert result.proposal.qty == .6 and result.closed_qty == .4
        assert result.exit_client_order_id is None
        # A distinct guardian invocation deliberately selects a fresh generation.
        c.place_order.side_effect = lambda **kw: ack(qty=kw['quantity'], executed=kw['quantity'], oid='next')
        final = await close_trade_position(result, client=c)
        assert final.proposal.qty == 0 and c.place_order.call_count == 2
        assert c.place_order.call_args.kwargs['client_order_id'] != selected[0]

    asyncio.run(scenario())


def test_inflight_replay_preserves_newer_active_generation(monkeypatch):
    async def scenario():
        t = record(); t.fees_known = True
        await trade_log.save_trade(t)
        c = client(); c.place_order = Mock(return_value=ack('CANCELED', 1, .4, oid='first-exit'))
        original = trade_log.prepare_exit
        ready, release = asyncio.Event(), asyncio.Event()

        async def controlled(trade_id, **kwargs):
            prepared = await original(trade_id, **kwargs)
            if asyncio.current_task().get_name() == 'paused-close' and not ready.is_set():
                ready.set()
                await release.wait()
            return prepared

        monkeypatch.setattr(trade_log, 'prepare_exit', controlled)
        a = asyncio.create_task(close_trade_position(t, client=c, client_order_id='first-close'),
                                name='paused-close')
        await asyncio.wait_for(ready.wait(), 5)
        try:
            await close_trade_position(t, client=c, client_order_id='first-close')
            await original(t.trade_id, client_order_id='newer-close')
        finally:
            release.set()
        updated = await a
        assert updated.closed_qty == .4 and updated.proposal.qty == .6
        assert updated.exit_client_order_id == 'newer-close'
        assert c.place_order.call_count == 1

    asyncio.run(scenario())


def test_entry_cannot_claim_id_reserved_for_tracked_exit():
    async def scenario():
        t = record(); t.fees_known = True
        await trade_log.save_trade(t)
        await trade_log.prepare_exit(t.trade_id, client_order_id='reserved-close')
        c = client(); c.place_order = Mock(return_value=ack(oid='entry-fill'))
        with pytest.raises(OrderNotDispatched, match='close'):
            await submit_order(OrderRequest(symbol='SOLUSDT', qty=1, client_order_id='reserved-close'),
                               client=c)
        c.place_order.assert_not_called()

    asyncio.run(scenario())


def test_stale_sizing_cannot_mark_newer_attempt_as_dust(monkeypatch):
    async def scenario():
        t = record(); t.fees_known = True
        await trade_log.save_trade(t)
        stale, current = client(), client()
        stale.get_price = Mock(return_value={'price': 1})
        stale.place_order = Mock()
        current.place_order = Mock(return_value=ack('CANCELED', 1, .4, oid='first-exit'))
        ready, release = asyncio.Event(), asyncio.Event()
        original = lifecycle.close_quantity

        async def controlled(trade, *, client):
            sized = await original(trade, client=client)
            if client is stale:
                assert sized[0] == 0
                ready.set()
                await release.wait()
            return sized

        monkeypatch.setattr(lifecycle, 'close_quantity', controlled)
        a = asyncio.create_task(close_trade_position(t, client=stale, client_order_id='first-close'))
        await asyncio.wait_for(ready.wait(), 5)
        try:
            await close_trade_position(t, client=current, client_order_id='first-close')
            await trade_log.prepare_exit(t.trade_id, client_order_id='newer-close')
        finally:
            release.set()
        replayed = await a
        assert replayed.closed_qty == .4 and replayed.proposal.qty == .6
        assert replayed.exit_client_order_id == 'newer-close'
        assert replayed.dust_qty == 0 and replayed.dust_reason is None
        stale.place_order.assert_not_called()
        assert current.place_order.call_count == 1

    asyncio.run(scenario())


def test_two_trades_cannot_reserve_same_id_after_both_owner_reads(monkeypatch):
    async def scenario():
        trades = [record(oid='entry1'), record(oid='entry2')]
        for t in trades:
            t.fees_known = True
            await trade_log.save_trade(t)
        c = client(); c.place_order = Mock(return_value=ack(oid='one-fill'))
        c.get_order_by_client_id = Mock(return_value=ack(oid='one-fill'))
        original = trade_log.prepare_exit
        arrived = 0
        ready = asyncio.Event()

        async def controlled(trade_id, **kwargs):
            nonlocal arrived
            if kwargs.get('client_order_id') == 'shared-close':
                arrived += 1
                if arrived == 2:
                    ready.set()
                await asyncio.wait_for(ready.wait(), 5)
            return await original(trade_id, **kwargs)

        monkeypatch.setattr(trade_log, 'prepare_exit', controlled)
        results = await asyncio.gather(*(close_trade_position(t, client=c,
            client_order_id='shared-close') for t in trades), return_exceptions=True)
        stored = [await trade_log.get_trade_by_id(t.trade_id) for t in trades]
        assert sum(t.closed_qty for t in stored) == 1
        assert sorted(t.proposal.qty for t in stored) == [0, 1]
        assert sum(isinstance(r, OrderOutcomeUnknown) for r in results) == 1
        assert c.place_order.call_count == 1

    asyncio.run(scenario())
