import pytest
from backend.marketdata.normalizer import normalize_agg_trade, normalize_depth_update
from backend.marketdata.models import Trade, BookDelta

def test_aggressor_side_derivation():
    """
    Mandatory aggressor rule test:
    Binance m = True means buyer was maker -> seller was aggressor -> side == "SELL".
    Binance m = False means seller was maker -> buyer was aggressor -> side == "BUY".
    """
    raw_sell = {
        "e": "aggTrade",
        "E": 1789671291000,
        "s": "BTCUSDT",
        "a": 1001,
        "p": "76600.50",
        "q": "0.25000",
        "f": 2001,
        "l": 2003,
        "T": 1789671290950,
        "m": True
    }
    trade_sell = normalize_agg_trade(raw_sell)
    assert trade_sell.side == "SELL"
    assert trade_sell.is_buyer_maker is True
    assert trade_sell.price == 76600.50
    assert trade_sell.qty == 0.25
    assert trade_sell.quote_qty == pytest.approx(76600.50 * 0.25)
    assert trade_sell.symbol == "BTCUSDT"
    assert trade_sell.agg_id == 1001

    raw_buy = {
        "e": "aggTrade",
        "E": 1789671292000,
        "s": "BTCUSDT",
        "a": 1002,
        "p": "76601.00",
        "q": "0.10000",
        "f": 2004,
        "l": 2004,
        "T": 1789671291990,
        "m": False
    }
    trade_buy = normalize_agg_trade(raw_buy)
    assert trade_buy.side == "BUY"
    assert trade_buy.is_buyer_maker is False
    assert trade_buy.price == 76601.00
    assert trade_buy.qty == 0.10
    assert trade_buy.quote_qty == pytest.approx(76601.00 * 0.10)

def test_combined_stream_wrapper_handling():
    """Tests normalizer unwrapping if Binance combined stream format is provided."""
    raw_wrapped = {
        "stream": "btcusdt@aggTrade",
        "data": {
            "e": "aggTrade",
            "E": 1789671293000,
            "s": "BTCUSDT",
            "a": 1003,
            "p": "76602.00",
            "q": "1.50000",
            "f": 2005,
            "l": 2008,
            "T": 1789671292990,
            "m": False
        }
    }
    trade = normalize_agg_trade(raw_wrapped)
    assert trade.symbol == "BTCUSDT"
    assert trade.side == "BUY"
    assert trade.agg_id == 1003
    assert trade.qty == 1.5

def test_depth_update_normalization():
    """Tests BookDelta normalization from Binance depth update stream."""
    raw_depth = {
        "e": "depthUpdate",
        "E": 1789671294000,
        "s": "BTCUSDT",
        "U": 5001,
        "u": 5010,
        "b": [["76600.00", "1.25000"], ["76599.00", "0.00000"]],
        "a": [["76601.00", "2.50000"], ["76602.00", "0.00000"]]
    }
    delta = normalize_depth_update(raw_depth)
    assert delta.symbol == "BTCUSDT"
    assert delta.first_update_id == 5001
    assert delta.final_update_id == 5010
    assert delta.bids == [[76600.0, 1.25], [76599.0, 0.0]]
    assert delta.asks == [[76601.0, 2.5], [76602.0, 0.0]]
    assert delta.event_ts == 1789671294000
