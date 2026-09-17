import pytest
from backend.marketdata.models import StreamHealth
from backend.engine.flow_models import FlowMetrics
from backend.engine.flow_confluence import evaluate_flow_confluence
from backend.engine.order_flow import evaluate_master_strategy_setup, OrderFlowAnalysis

@pytest.fixture
def base_metrics():
    return FlowMetrics(
        symbol="BTCUSDT",
        ts=1000,
        price=60000.0,
        session_cvd=100.0,
        bar_delta=50.0,
        delta_percent=0.1,
        cvd_slope=0.5,
        cvd_divergence=None,
        buy_sell_ratio=1.2,
        aggression_index=0.6,
        absorption_flag=None,
        stacked_imbalance_bias="NEUTRAL",
        poc_price=60000.0,
        vah=60500.0,
        val=59500.0,
        price_vs_value="IN_VALUE",
        book_imbalance=0.0,
        spread_bps=1.0,
        nearest_bid_wall=59000.0,
        nearest_ask_wall=61000.0,
        vwap=60000.0,
        vwap_upper_1=61000.0,
        vwap_lower_1=59000.0,
        trade_rate=5.0,
        volume_rate=10.0,
        health=StreamHealth(
            symbol="BTCUSDT", connected=True, streams=[], last_trade_ts=1000,
            last_book_ts=1000, messages_per_sec=10, reconnects=0, book_resyncs=0,
            gap_events=0, lag_ms=0, status="LIVE"
        )
    )

def test_confluence_veto_stale_health(base_metrics):
    base_metrics.health.status = "DISCONNECTED"
    res = evaluate_flow_confluence("BTCUSDT", base_metrics, [1]*20, "BUY")
    assert res["veto"] == True
    assert "not live" in res["veto_reason"].lower()

def test_confluence_veto_spread(base_metrics):
    base_metrics.spread_bps = 10.0
    res = evaluate_flow_confluence("BTCUSDT", base_metrics, [1]*20, "BUY")
    assert res["veto"] == True
    assert "spread too wide" in res["veto_reason"].lower()

def test_confluence_scoring_bullish(base_metrics):
    base_metrics.cvd_slope = 1.0
    base_metrics.session_cvd = 500.0
    base_metrics.stacked_imbalance_bias = "BUY"
    base_metrics.absorption_flag = "SELL_ABSORBED"
    base_metrics.book_imbalance = 0.2
    base_metrics.price = 59600.0
    base_metrics.val = 59500.0

    res = evaluate_flow_confluence("BTCUSDT", base_metrics, [1]*20, "BUY")
    assert res["veto"] == False
    assert res["score"] == 1.0 # 0.3 + 0.25 + 0.2 + 0.15 + 0.10

def test_confluence_regression_master_strategy():
    order_flow = OrderFlowAnalysis(
        symbol="BTCUSDT",
        timestamp="2026-09-17",
        current_price=60000.0,
        trend_bias="BULLISH",
        order_blocks=[],
        fair_value_gaps=[],
        unfilled_fvgs=[]
    )
    # Without flow
    res1 = evaluate_master_strategy_setup("BTCUSDT", 60000.0, order_flow, None)
    # With shadow flow (but disabled in settings)
    res2 = evaluate_master_strategy_setup("BTCUSDT", 60000.0, order_flow, None, flow={"score": 1.0, "veto": False, "reasons": []})
    
    from backend.config import settings
    # When disabled, should be identical
    if getattr(settings, "FLOW_CONFLUENCE_ENABLED", False) == False:
        assert res1["score"] == res2["score"]
