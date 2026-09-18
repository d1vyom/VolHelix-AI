import pytest
from backend.models.market import OptionLeg, StrategyType
from backend.engine.strategy_builder import build_master_order_flow_strategy

def test_build_master_order_flow_strategy_aggregates_greeks_and_levels():
    call_leg = OptionLeg(action="BUY", contract_type="CALL", strike=65000.0, expiry="2026-04-15", symbol="BTC_C65000", premium=1200.0, delta=0.45, theta=-0.20, vega=0.30)
    put_leg = OptionLeg(action="BUY", contract_type="PUT", strike=60000.0, expiry="2026-04-15", symbol="BTC_P60000", premium=900.0, delta=-0.40, theta=-0.15, vega=0.25)

    prop = build_master_order_flow_strategy(
        underlying="BTCUSDT",
        legs=[call_leg, put_leg],
        is_credit=False,
        net_premium=-2100.0,
        max_profit=4000.0,
        max_loss=2100.0,
        breakevens=[58500.0, 66500.0],
        dte=30,
        thesis="Master Flow OB + FVG confluence",
        take_profit=66500.0,
        stop_loss=58500.0
    )

    assert prop.strategy_type == StrategyType.MASTER_ORDER_FLOW
    assert prop.is_credit is False
    assert prop.net_premium == -2100.0
    assert prop.max_profit == 4000.0
    assert prop.max_loss == 2100.0
    assert prop.breakevens == [58500.0, 66500.0]
    # Net greeks are the sum across legs, rounded to 3dp
    assert prop.net_delta == 0.05
    assert prop.net_theta == -0.35
    assert prop.net_vega == 0.55
    # Dynamic TP/SL anchors from the Master Strategy are carried through
    assert prop.take_profit == 66500.0
    assert prop.stop_loss == 58500.0
