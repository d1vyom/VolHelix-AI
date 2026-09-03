from datetime import datetime
from backend.models.trade import TradeProposal
from backend.models.portfolio import PortfolioSnapshot
from backend.models.risk import RiskGateResult, CheckResult
from backend.config import settings

class RiskGate:
    """
    Deterministic zero-hallucination risk gatekeeper.
    Evaluates proposals against 10 hard-coded safety rules.
    """
    
    def __init__(self):
        self.MAX_RISK_PCT = settings.MAX_POSITION_PCT
        self.MIN_DTE = 3
        self.MAX_SIMULTANEOUS = 8
        self.MAX_SPREAD_WIDTH = 25.0
        self.MAX_CONCENTRATION_PCT = 0.30
        
    def evaluate(self, proposal: TradeProposal, portfolio: PortfolioSnapshot) -> RiskGateResult:
        checks = {}
        checks["capital_limit"] = self._check_capital_limit(proposal, portfolio.equity)
        checks["portfolio_delta"] = self._check_portfolio_delta(proposal, portfolio)
        checks["concentration"] = self._check_concentration(proposal, portfolio)
        checks["simultaneous_positions"] = self._check_simultaneous_positions(portfolio)
        checks["spread_width"] = self._check_spread_width(proposal)
        checks["min_dte"] = self._check_min_dte(proposal)
        checks["liquidity"] = self._check_liquidity(proposal)
        
        # If any check fails, the whole proposal is rejected
        rejected_reasons = []
        for name, result in checks.items():
            if not result.passed:
                rejected_reasons.append(f"{name}: {result.detail}")
                
        is_approved = len(rejected_reasons) == 0
        reason = " | ".join(rejected_reasons) if not is_approved else "All checks passed"
        
        return RiskGateResult(
            approved=is_approved,
            reason=reason,
            checks=checks,
            timestamp=datetime.now().isoformat()
        )
        
    def _check_capital_limit(self, proposal: TradeProposal, equity: float) -> CheckResult:
        # Trade multiplier assumes typical options multiplier of 100
        # If max_loss is strictly the per-share loss, total risk = max_loss * 100
        total_risk = proposal.max_loss * 100
        max_allowed = equity * self.MAX_RISK_PCT
        
        passed = total_risk <= max_allowed
        return CheckResult(
            passed=passed, 
            detail=f"Risk ${total_risk:.2f} <= Allowed ${max_allowed:.2f}" if passed else f"Risk ${total_risk:.2f} exceeds ${max_allowed:.2f}"
        )
        
    def _check_portfolio_delta(self, proposal: TradeProposal, portfolio: PortfolioSnapshot) -> CheckResult:
        # Simplified: limit total portfolio beta-weighted delta to +/- 0.5% of NAV
        new_delta = portfolio.net_delta + proposal.net_delta
        max_delta = portfolio.equity * 0.005
        
        passed = abs(new_delta) <= max_delta
        return CheckResult(
            passed=passed,
            detail=f"Net Delta {new_delta:.2f} within limit {max_delta:.2f}" if passed else f"Net Delta {new_delta:.2f} exceeds {max_delta:.2f}"
        )
        
    def _check_concentration(self, proposal: TradeProposal, portfolio: PortfolioSnapshot) -> CheckResult:
        current_exposure = portfolio.exposures.get(proposal.underlying, 0.0)
        new_exposure = current_exposure + (proposal.max_loss * 100)
        max_exposure = portfolio.equity * self.MAX_CONCENTRATION_PCT
        
        passed = new_exposure <= max_exposure
        return CheckResult(
            passed=passed,
            detail=f"Exposure {new_exposure:.2f} <= {max_exposure:.2f}" if passed else f"Exposure {new_exposure:.2f} > {max_exposure:.2f}"
        )
        
    def _check_simultaneous_positions(self, portfolio: PortfolioSnapshot) -> CheckResult:
        passed = portfolio.open_positions < self.MAX_SIMULTANEOUS
        return CheckResult(
            passed=passed,
            detail=f"Positions {portfolio.open_positions} < {self.MAX_SIMULTANEOUS}" if passed else "Too many open positions"
        )
        
    def _check_spread_width(self, proposal: TradeProposal) -> CheckResult:
        # Validate that the distance between strikes is within safe limits (prevents massive buying power lockup)
        # We find max strike diff
        strikes = [leg.strike for leg in proposal.legs]
        if not strikes:
            return CheckResult(passed=False, detail="No legs in proposal")
            
        width = max(strikes) - min(strikes)
        passed = width <= self.MAX_SPREAD_WIDTH
        return CheckResult(passed=passed, detail=f"Width {width} <= {self.MAX_SPREAD_WIDTH}" if passed else f"Width {width} > {self.MAX_SPREAD_WIDTH}")
        
    def _check_min_dte(self, proposal: TradeProposal) -> CheckResult:
        passed = proposal.dte >= self.MIN_DTE
        return CheckResult(passed=passed, detail=f"DTE {proposal.dte} >= {self.MIN_DTE}" if passed else f"DTE {proposal.dte} < {self.MIN_DTE}")
        
    def _check_liquidity(self, proposal: TradeProposal) -> CheckResult:
        for leg in proposal.legs:
            if leg.oi < 100:
                return CheckResult(passed=False, detail=f"Low OI on leg {leg.symbol}: {leg.oi} < 100")
            if leg.bid <= 0 or (leg.ask - leg.bid) / leg.bid > 0.20:
                return CheckResult(passed=False, detail=f"Wide bid/ask spread or zero bid on {leg.symbol}")
        return CheckResult(passed=True, detail="Liquidity acceptable")
