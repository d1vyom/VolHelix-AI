"""Exact exchange price grids at decimal boundaries and below eight places."""
import pytest

from backend.config import settings
from backend.engine.footprint import FootprintEngine, round_to_tick
from backend.engine.heatmap import HeatmapEngine
from backend.engine.volume_profile import VolumeProfileEngine, compute_profile_from_trades
from backend.marketdata.models import BookSnapshot, Trade
from backend.marketdata.orderbook import LocalOrderBook


@pytest.mark.parametrize('price,tick,expected', [
    (0.3, 0.1, 0.3), (0.299, 0.1, 0.2), (0.301, 0.1, 0.3),
    (3e-9, 1e-9, 3e-9), (3.9e-9, 1e-9, 3e-9),
    (1.23e-12, 1e-14, 1.23e-12),
])
def test_floor_tick_keeps_exact_decimal_boundaries(price, tick, expected):
    assert round_to_tick(price, tick) == expected


def trade(price, qty, agg_id):
    return Trade(symbol='TINYUSDT', agg_id=agg_id, price=price, qty=qty,
                 quote_qty=price*qty, ts=agg_id*1000, side='BUY',
                 is_buyer_maker=False, first_id=agg_id, last_id=agg_id)


@pytest.mark.parametrize('tick,multiplier,price,expected', [(0.1, 3, 0.3, 0.3), (1e-9, 3, 3e-9, 3e-9)])
def test_engines_share_decimal_group_and_preserve_grouped_volume(monkeypatch, tick, multiplier, price, expected):
    monkeypatch.setattr(settings, 'FLOW_TICK_GROUP_MULTIPLIER', multiplier)
    footprint = FootprintEngine('TINYUSDT', '1m', tick)
    profile = VolumeProfileEngine('TINYUSDT', tick)
    heatmap = HeatmapEngine('TINYUSDT', tick)
    assert footprint.tick_group == profile.tick_group == heatmap.tick_group == expected
    trades = [trade(price, 2, 1), trade(price + tick/10, 5, 2)]
    for item in trades:
        footprint.process_trade(item)
        profile.process_trade(item)
    assert list(footprint.cells_dict) == [expected]
    assert footprint.cells_dict[expected].total_volume == 7
    assert list(profile.levels_dict) == [expected]
    assert profile.levels_dict[expected].total_volume == 7
    visible = compute_profile_from_trades('TINYUSDT', trades, 'VISIBLE', 0, 10000, expected)
    assert [(row.price, row.total_volume) for row in visible.levels] == [(expected, 7)]
    frame = heatmap.process_book(BookSnapshot(symbol='TINYUSDT', last_update_id=1,
        bids=[[price, 2], [price + tick/10, 5]], asks=[], ts=1, source='REST'))
    assert frame.levels == [[expected, 7, 0]]


@pytest.mark.parametrize('tick,multiplier,bids,asks,expected', [
    (0.1, 1, [[0.3,2],[0.31,5]], [[0.3,3],[0.29,4]], [(0.3,7,7)]),
    (0.1, 3, [[0.3,2],[0.31,5]], [[0.3,3],[0.29,4]], [(0.3,7,7)]),
    (1e-9, 1, [[3e-9,2],[3.1e-9,5]], [[4e-9,3],[3.9e-9,4]], [(4e-9,0,7),(3e-9,7,0)]),
])
def test_dom_floors_bids_ceils_asks_without_shifting_exact_prices(tick, multiplier, bids, asks, expected):
    book = LocalOrderBook('TINYUSDT', tick)
    book.apply_partial({'bids':bids,'asks':asks})
    rows = book.get_ladder(tick_group_multiplier=multiplier)
    assert [(row.price, row.bid_size, row.ask_size) for row in rows] == expected
