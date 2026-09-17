import pytest
from backend.risk.risk_gate import CryptoRiskGate
from backend.models.trade import TradeProposal
from backend.models.market import Regime

def test_risk_gate_approves_valid_crypto_proposal(base_portfolio, sample_crypto_proposal):
    gate = CryptoRiskGate()
    result = gate.evaluate(sample_crypto_proposal, base_portfolio)
    assert result.approved is True
    assert "All 10 checks passed" in result.reason
    assert result.checks["capital_limit"].passed is True
    assert result.checks["stop_loss"].passed is True
    assert result.checks["take_profit"].passed is True
    assert result.checks["min_order_size"].passed is True
    assert result.checks["simultaneous_positions"].passed is True

def test_risk_gate_rejects_exceeding_capital_limit(base_portfolio, sample_crypto_proposal):
    gate = CryptoRiskGate()
    # 2.5% of 100,000 is 2,500. Set qty to 0.1 at $60,000 ($6,000 value > $2,500)
    sample_crypto_proposal.qty = 0.1
    result = gate.evaluate(sample_crypto_proposal, base_portfolio)
    assert result.approved is False
    assert result.checks["capital_limit"].passed is False
    assert "capital_limit" in result.reason

def test_risk_gate_rejects_missing_stop_loss(base_portfolio, sample_crypto_proposal):
    gate = CryptoRiskGate()
    sample_crypto_proposal.stop_loss = 0.0
    result = gate.evaluate(sample_crypto_proposal, base_portfolio)
    assert result.approved is False
    assert result.checks["stop_loss"].passed is False

def test_risk_gate_rejects_missing_take_profit(base_portfolio, sample_crypto_proposal):
    gate = CryptoRiskGate()
    sample_crypto_proposal.take_profit = 0.0
    result = gate.evaluate(sample_crypto_proposal, base_portfolio)
    assert result.approved is False
    assert result.checks["take_profit"].passed is False

def test_risk_gate_rejects_min_order_size(base_portfolio, sample_crypto_proposal):
    gate = CryptoRiskGate()
    # Binance spot requires >= $10.00 USDT
    sample_crypto_proposal.qty = 0.0001
    sample_crypto_proposal.entry_price = 60000.0  # $6.00 value
    result = gate.evaluate(sample_crypto_proposal, base_portfolio)
    assert result.approved is False
    assert result.checks["min_order_size"].passed is False

def test_risk_gate_rejects_drawdown_circuit_breaker(base_portfolio, sample_crypto_proposal):
    gate = CryptoRiskGate()
    # Daily DD >= 3.0% of 100,000 ($3,000)
    base_portfolio.daily_pnl = -3500.0
    result = gate.evaluate(sample_crypto_proposal, base_portfolio)
    assert result.approved is False
    assert result.checks["drawdown_circuit_breaker"].passed is False

def test_risk_gate_rejects_too_many_open_positions(base_portfolio, sample_crypto_proposal):
    gate = CryptoRiskGate()
    base_portfolio.open_positions = 5  # Limit is 5
    result = gate.evaluate(sample_crypto_proposal, base_portfolio)
    assert result.approved is False
    assert result.checks["simultaneous_positions"].passed is False

def test_risk_gate_rejects_single_asset_concentration(base_portfolio, sample_crypto_proposal):
    gate = CryptoRiskGate()
    # Max concentration is 30% ($30,000). Existing BTC is $29,000 + new $2,000 = $31,000
    base_portfolio.exposures["BTC"] = 29000.0
    sample_crypto_proposal.qty = 0.035
    sample_crypto_proposal.entry_price = 60000.0  # $2,100
    result = gate.evaluate(sample_crypto_proposal, base_portfolio)
    assert result.approved is False
    assert result.checks["single_asset_concentration"].passed is False

def test_risk_gate_handles_regime_sizing_multiplier(base_portfolio, sample_crypto_proposal):
    gate = CryptoRiskGate()
    result = gate.evaluate(sample_crypto_proposal, base_portfolio, regime=Regime.SQUEEZE)
    assert result.checks["volatility_sizing"].passed is True
    assert "0.50x" in result.checks["volatility_sizing"].detail
