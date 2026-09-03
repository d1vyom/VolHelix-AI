import pytest
from backend.engine.order_flow import (
    OrderBlock,
    FairValueGap,
    OrderFlowAnalysis,
    calculate_master_strategy_tp_sl
)
from backend.engine.gamma_profile import GammaProfile
from backend.engine.auto_trader import AutoTrader

def test_calculate_master_strategy_dynamic_tp_sl_bullish():
    spot_price = 580.0
    bullish_ob = OrderBlock(
        id="OB-1",
        block_type="BULLISH",
        low=572.0,
        high=575.0,
        mean_threshold=573.5,
        volume=2500,
        timestamp="2026-09-03",
        mitigated=False,
        strength=0.9
    )
    unfilled_fvg = FairValueGap(
        id="FVG-1",
        gap_type="BEARISH",
        top=602.0,
        bottom=598.0,
        midpoint=600.0,
        size=4.0,
        timestamp="2026-09-03",
        filled=False,
        fill_pct=0.0
    )
    of = OrderFlowAnalysis(
        symbol="SPY",
        timestamp="2026-09-03",
        current_price=spot_price,
        trend_bias="BULLISH",
        nearest_bullish_ob=bullish_ob,
        unfilled_fvgs=[unfilled_fvg]
    )
    gamma = GammaProfile(
        spot_price=spot_price,
        total_net_gex=15.2,
        call_wall=605.0,
        put_wall=570.0,
        gamma_flip=575.0,
        regime="POSITIVE_GAMMA",
        levels=[]
    )

    result = calculate_master_strategy_tp_sl("SPY", spot_price, of, gamma, trend_bias="BULLISH")
    
    assert result["entry_price"] == 580.0
    # Stop Loss should be anchored below Bullish OB low (572.0 - 0.25 = 571.75)
    assert result["stop_loss_price"] <= 572.0
    assert "Bullish OB Invalidation" in result["sl_reason"]
    # Take Profit should target the FVG bottom (598.0)
    assert result["take_profit_price"] == 598.0
    assert "FVG Imbalance Fill" in result["tp_reason"]
    # Risk Reward ratio should be greater than 2.0
    assert result["risk_reward_ratio"] >= 2.0

def test_auto_trader_singleton_and_status():
    trader = AutoTrader()
    assert trader is not None
    assert "SPY" in trader.watched_symbols
    assert trader.max_open_positions == 3
    
    status = trader.status()
    assert "is_running" in status
    assert "total_automated_trades" in status
    assert "watched_symbols" in status

def test_auto_trader_start_stop_lifecycle():
    trader = AutoTrader()
    # Ensure stopped
    trader.stop()
    assert trader.is_running is False
    
    # Start
    start_res = trader.start(interval=60)
    assert start_res["success"] is True
    assert trader.is_running is True
    assert trader.interval_seconds == 60
    
    # Stop
    stop_res = trader.stop()
    assert stop_res["success"] is True
    assert trader.is_running is False

def test_evaluate_master_strategy_setup_high_confluence():
    from backend.engine.order_flow import evaluate_master_strategy_setup
    spot_price = 575.0
    bullish_ob = OrderBlock(
        id="OB-BULL",
        block_type="BULLISH",
        low=572.0,
        high=574.5,
        mean_threshold=573.25,
        volume=3000,
        timestamp="2026-09-04",
        mitigated=False,
        strength=0.95
    )
    unfilled_fvg = FairValueGap(
        id="FVG-UP",
        gap_type="BEARISH",
        top=595.0,
        bottom=590.0,
        midpoint=592.5,
        size=5.0,
        timestamp="2026-09-04",
        filled=False,
        fill_pct=0.0
    )
    of = OrderFlowAnalysis(
        symbol="SPY",
        timestamp="2026-09-04",
        current_price=spot_price,
        trend_bias="BULLISH",
        nearest_bullish_ob=bullish_ob,
        unfilled_fvgs=[unfilled_fvg]
    )
    gamma = GammaProfile(
        spot_price=spot_price,
        total_net_gex=18.5,
        call_wall=600.0,
        put_wall=570.0,
        gamma_flip=572.0,
        regime="POSITIVE_GAMMA",
        levels=[]
    )

    eval_res = evaluate_master_strategy_setup("SPY", spot_price, of, gamma)
    assert eval_res["is_valid"] is True
    assert eval_res["score"] >= 0.70
    assert eval_res["status_label"] == "CONFLUENCE CONFIRMED"
    assert "Bullish OB Demand Retest" in eval_res["reasons"][0]

def test_evaluate_master_strategy_setup_rejects_without_confluence():
    from backend.engine.order_flow import evaluate_master_strategy_setup
    spot_price = 575.0
    # No OB and no FVG
    of = OrderFlowAnalysis(
        symbol="SPY",
        timestamp="2026-09-04",
        current_price=spot_price,
        trend_bias="NEUTRAL",
        unfilled_fvgs=[]
    )
    eval_res = evaluate_master_strategy_setup("SPY", spot_price, of, None)
    assert eval_res["is_valid"] is False
    assert eval_res["score"] < 0.70
    assert eval_res["status_label"] != "CONFLUENCE CONFIRMED"

def test_position_guardian_remains_active_when_auto_pilot_is_stopped():
    trader = AutoTrader()
    trader.ensure_guardian_running()
    
    # Auto-Pilot is explicitly stopped
    trader.stop()
    assert trader.is_running is False
    
    # Position Guardian must STILL be active
    status = trader.status()
    assert status["is_running"] is False
    assert status["guardian_active"] is True

def test_trigger_cycle_scans_only_target_symbol():
    from unittest.mock import patch, MagicMock
    trader = AutoTrader()
    trader.stop()

    with patch.object(trader, "_get_trading_client") as mock_tc, \
         patch("backend.engine.auto_trader.AlpacaClient") as mock_mcp, \
         patch.object(trader, "_get_stock_client") as mock_sc, \
         patch.object(trader, "ensure_guardian_running"):
        
        mock_tc.return_value.get_all_positions.return_value = []
        mock_mcp.return_value.get_stock_bars.return_value = {"bars": []}
        mock_mcp.return_value.get_option_chain.return_value = {"legs": []}
        
        # When user triggers scan for AAPL only
        res = trader.trigger_cycle(symbol="AAPL")
        
        assert res["success"] is True
        assert res.get("symbol") == "AAPL"
        # Verify get_stock_bars was called ONLY for AAPL, NOT SPY/QQQ/NVDA/TSLA
        calls = [c.args[0] for c in mock_mcp.return_value.get_stock_bars.call_args_list]
        assert calls == ["AAPL"]
