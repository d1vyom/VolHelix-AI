import pytest
from backend.risk.risk_gate import RiskGate
from backend.models.market import OptionLeg, StrategyType
from backend.models.trade import TradeProposal

def test_risk_gate_approves_valid_proposal(base_portfolio, sample_bull_put_proposal):
    gate = RiskGate()
    result = gate.evaluate(sample_bull_put_proposal, base_portfolio)
    assert result.approved is True
    assert "All checks passed" in result.reason
    assert result.checks["capital_limit"].passed is True
    assert result.checks["min_dte"].passed is True
    assert result.checks["liquidity"].passed is True

def test_risk_gate_rejects_exceeding_capital_limit(base_portfolio, sample_bull_put_proposal):
    gate = RiskGate()
    # 2.5% of 100,000 is 2,500. Set max_loss to 30.0 ($3,000 risk)
    sample_bull_put_proposal.max_loss = 30.0
    result = gate.evaluate(sample_bull_put_proposal, base_portfolio)
    assert result.approved is False
    assert result.checks["capital_limit"].passed is False
    assert "capital_limit" in result.reason

def test_risk_gate_rejects_low_dte(base_portfolio, sample_bull_put_proposal):
    gate = RiskGate()
    sample_bull_put_proposal.dte = 2  # Min is 3
    result = gate.evaluate(sample_bull_put_proposal, base_portfolio)
    assert result.approved is False
    assert result.checks["min_dte"].passed is False

def test_risk_gate_rejects_wide_spread_width(base_portfolio, sample_bull_put_proposal):
    gate = RiskGate()
    # Spread width > 25.0
    sample_bull_put_proposal.legs[0].strike = 550.0
    sample_bull_put_proposal.legs[1].strike = 500.0  # Width = 50
    result = gate.evaluate(sample_bull_put_proposal, base_portfolio)
    assert result.approved is False
    assert result.checks["spread_width"].passed is False

def test_risk_gate_rejects_too_many_open_positions(base_portfolio, sample_bull_put_proposal):
    gate = RiskGate()
    base_portfolio.open_positions = 8  # Max simultaneous is 8
    result = gate.evaluate(sample_bull_put_proposal, base_portfolio)
    assert result.approved is False
    assert result.checks["simultaneous_positions"].passed is False

def test_risk_gate_rejects_low_open_interest(base_portfolio, sample_bull_put_proposal):
    gate = RiskGate()
    sample_bull_put_proposal.legs[0].oi = 50  # Must be >= 100
    result = gate.evaluate(sample_bull_put_proposal, base_portfolio)
    assert result.approved is False
    assert result.checks["liquidity"].passed is False

def test_risk_gate_rejects_wide_bid_ask_spread(base_portfolio, sample_bull_put_proposal):
    gate = RiskGate()
    # bid=1.00, ask=1.35 -> spread is 35% > 20%
    sample_bull_put_proposal.legs[0].bid = 1.00
    sample_bull_put_proposal.legs[0].ask = 1.35
    result = gate.evaluate(sample_bull_put_proposal, base_portfolio)
    assert result.approved is False
    assert result.checks["liquidity"].passed is False

def test_risk_gate_rejects_portfolio_delta_overload(base_portfolio, sample_bull_put_proposal):
    gate = RiskGate()
    # Max delta is 0.5% of 100k = 500. Set portfolio delta to 490 and prop to 25 -> 515 > 500
    base_portfolio.net_delta = 490.0
    sample_bull_put_proposal.net_delta = 25.0
    result = gate.evaluate(sample_bull_put_proposal, base_portfolio)
    assert result.approved is False
    assert result.checks["portfolio_delta"].passed is False

def test_risk_gate_rejects_single_stock_concentration(base_portfolio, sample_bull_put_proposal):
    gate = RiskGate()
    # Max concentration is 30% of 100k = $30,000. Existing exposure $29,000 + $350 risk
    base_portfolio.exposures["SPY"] = 29900.0
    sample_bull_put_proposal.max_loss = 5.0  # $500 risk -> $30,400 > $30,000
    result = gate.evaluate(sample_bull_put_proposal, base_portfolio)
    assert result.approved is False
    assert result.checks["concentration"].passed is False
