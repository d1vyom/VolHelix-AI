import os
import sys
import pytest
from datetime import datetime

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.models.portfolio import PortfolioSnapshot
from backend.models.market import Regime, Trend, OptionLeg, StrategyType, MarketSignal, RiskFlags
from backend.models.trade import TradeProposal

@pytest.fixture
def base_portfolio():
    return PortfolioSnapshot(
        timestamp=datetime.now().isoformat(),
        equity=100000.0,
        buying_power=100000.0,
        daily_pnl=0.0,
        total_pnl=0.0,
        open_positions=0,
        net_delta=0.0,
        net_theta=0.0,
        net_vega=0.0,
        current_regime=Regime.NORMAL,
        exposures={}
    )

@pytest.fixture
def sample_legs():
    short_put = OptionLeg(
        action="SELL",
        contract_type="PUT",
        strike=500.0,
        expiry="2026-04-15",
        symbol="SPY260415P00500000",
        premium=4.50,
        delta=-0.25,
        gamma=0.02,
        theta=0.15,
        vega=-0.12,
        oi=500,
        bid=4.40,
        ask=4.60
    )
    long_put = OptionLeg(
        action="BUY",
        contract_type="PUT",
        strike=495.0,
        expiry="2026-04-15",
        symbol="SPY260415P00495000",
        premium=3.00,
        delta=0.15,
        gamma=-0.01,
        theta=-0.10,
        vega=0.08,
        oi=400,
        bid=2.90,
        ask=3.10
    )
    return short_put, long_put

@pytest.fixture
def sample_bull_put_proposal(sample_legs):
    short_put, long_put = sample_legs
    return TradeProposal(
        id="test-prop-001",
        underlying="SPY",
        strategy_type=StrategyType.BULL_PUT_SPREAD,
        legs=[short_put, long_put],
        is_credit=True,
        net_premium=1.50,
        max_profit=1.50,
        max_loss=3.50,  # $350 risk per contract
        breakevens=[498.50],
        net_delta=-0.10,
        net_theta=0.05,
        net_vega=-0.04,
        dte=30,
        ev=1.10,
        thesis="Bullish support bounce at 500"
    )

@pytest.fixture
def sample_market_signal():
    return MarketSignal(
        timestamp=datetime.now().isoformat(),
        underlying="SPY",
        price=510.0,
        iv_current=0.16,
        iv_rank=0.35,
        iv_percentile=0.40,
        regime=Regime.NORMAL,
        trend=Trend.BULLISH,
        thesis="Steady uptrend with moderate volatility",
        confidence=0.85
    )

@pytest.fixture
def clean_risk_flags():
    return RiskFlags(
        events=[],
        risk_level="LOW",
        size_modifier=1.0
    )
