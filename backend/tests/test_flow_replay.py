import pytest
import os
import json
from backend.marketdata.models import StreamHealth, Trade

def test_stream_health_status_live():
    health = StreamHealth(
        symbol="BTCUSDT",
        connected=True,
        streams=["REPLAY"],
        last_trade_ts=1000,
        last_book_ts=1000,
        messages_per_sec=10.0,
        reconnects=0,
        book_resyncs=0,
        gap_events=0,
        lag_ms=0,
        status="LIVE"
    )
    assert health.status == "LIVE"
    assert health.symbol == "BTCUSDT"

def test_stream_health_status_disconnected():
    health = StreamHealth(
        symbol="ETHUSDT",
        connected=False,
        streams=[],
        last_trade_ts=0,
        last_book_ts=0,
        messages_per_sec=0.0,
        reconnects=1,
        book_resyncs=0,
        gap_events=0,
        lag_ms=1000,
        status="DISCONNECTED"
    )
    assert health.status == "DISCONNECTED"
    assert health.connected is False

def test_trade_aggressor_side_sell():
    # When m=True (maker is buyer), aggressor is SELLER
    trade = Trade(
        symbol="BTCUSDT",
        agg_id=1,
        price=100.0,
        qty=1.0,
        quote_qty=100.0,
        ts=1000,
        is_buyer_maker=True,
        side="SELL",
        first_id=1,
        last_id=1
    )
    assert trade.side == "SELL"

def test_trade_aggressor_side_buy():
    # When m=False (maker is seller), aggressor is BUYER
    trade = Trade(
        symbol="BTCUSDT",
        agg_id=1,
        price=100.0,
        qty=1.0,
        quote_qty=100.0,
        ts=1000,
        is_buyer_maker=False,
        side="BUY",
        first_id=1,
        last_id=1
    )
    assert trade.side == "BUY"
