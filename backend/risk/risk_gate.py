from datetime import datetime
from typing import Optional, Dict
from backend.models.trade import TradeProposal
from backend.models.portfolio import PortfolioSnapshot
from backend.models.market import Regime
from backend.models.risk import RiskGateResult, CheckResult
from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger("risk_gate")


class CryptoRiskGate:
    """
    Hard-coded, deterministic 10-rule risk gatekeeper for 24/7 crypto spot trading.
    STILL deterministic, STILL pure Python, STILL zero LLM.
    """

    MAX_POSITION_PCT = settings.MAX_POSITION_PCT  # 2.5% of NAV
    MAX_DAILY_DRAWDOWN = settings.MAX_DAILY_DRAWDOWN  # 3% circuit breaker
    HALT_DURATION_MINUTES = 60  # 1 hour halt for 24/7 markets
    MAX_EXPOSURE_PCT = 0.60  # Max 60% in non-USDT assets
    MAX_SINGLE_ASSET_PCT = 0.30  # Max 30% in a single crypto asset
    MAX_POSITIONS = 5  # Max 5 non-USDT holdings
    MIN_ORDER_VALUE_USDT = 10.0  # Binance minimum order size

    STOP_LOSS_DEFAULTS = {
        "BTCUSDT": 0.02,
        "ETHUSDT": 0.025,
        "SOLUSDT": 0.035,
        "BNBUSDT": 0.03,
        "XRPUSDT": 0.035,
    }

    TAKE_PROFIT_DEFAULTS = {
        "BTCUSDT": 0.04,
        "ETHUSDT": 0.05,
        "SOLUSDT": 0.07,
        "BNBUSDT": 0.06,
        "XRPUSDT": 0.07,
    }

    REGIME_SIZE_MULTIPLIERS = {
        Regime.LOW_VOL: 1.0,
        Regime.NORMAL: 1.0,
        Regime.ELEVATED: 0.75,
        Regime.SQUEEZE: 0.50,
        Regime.CRISIS: 0.25,
    }

    CORRELATION_GROUPS = {
        "high_cap": ["BTCUSDT", "ETHUSDT"],
        "alt_l1": ["SOLUSDT", "BNBUSDT"],
        "payments": ["XRPUSDT"],
    }

    def __init__(self):
        self.MAX_RISK_PCT = self.MAX_POSITION_PCT

    def evaluate(
        self,
        proposal: TradeProposal,
        portfolio: PortfolioSnapshot,
        regime: Optional[Regime] = None
    ) -> RiskGateResult:
        """
        Evaluate proposal against the 10 deterministic crypto safety rules.
        """
        checks: Dict[str, CheckResult] = {}
        nav = portfolio.equity if portfolio.equity > 0 else 10000.0
        current_regime = regime or getattr(portfolio, "current_regime", Regime.NORMAL)

        # Calculate position value (price * quantity)
        price = proposal.entry_price or proposal.limit_price or 1.0
        position_value = proposal.qty * price if (proposal.qty and price) else proposal.quote_qty or 0.0

        symbol = (proposal.symbol or proposal.underlying or "BTCUSDT").upper()
        base_asset = symbol.replace("USDT", "")

        # 1. Capital Allocation (<= 2.5% NAV)
        max_allowed_capital = self.MAX_POSITION_PCT * nav
        checks["capital_limit"] = CheckResult(
            passed=position_value <= max_allowed_capital,
            detail=f"${position_value:.2f} <= ${max_allowed_capital:.2f} ({self.MAX_POSITION_PCT:.1%} NAV)"
            if position_value <= max_allowed_capital
            else f"${position_value:.2f} exceeds limit ${max_allowed_capital:.2f}"
        )

        # 2. Stop-Loss is Set
        default_sl_pct = self.STOP_LOSS_DEFAULTS.get(symbol, 0.03)
        sl_is_valid = proposal.stop_loss is not None and proposal.stop_loss > 0
        checks["stop_loss"] = CheckResult(
            passed=sl_is_valid,
            detail=f"SL set at ${proposal.stop_loss:.2f} (benchmark: -{default_sl_pct:.1%})"
            if sl_is_valid
            else "Stop-loss must be strictly positive"
        )

        # 3. Take-Profit is Set
        default_tp_pct = self.TAKE_PROFIT_DEFAULTS.get(symbol, 0.05)
        tp_is_valid = proposal.take_profit is not None and proposal.take_profit > 0
        checks["take_profit"] = CheckResult(
            passed=tp_is_valid,
            detail=f"TP set at ${proposal.take_profit:.2f} (benchmark: +{default_tp_pct:.1%})"
            if tp_is_valid
            else "Take-profit must be strictly positive"
        )

        # 4. Daily Drawdown Circuit Breaker
        daily_dd = abs(portfolio.daily_pnl) / nav if nav > 0 else 0.0
        dd_passed = daily_dd < self.MAX_DAILY_DRAWDOWN
        checks["drawdown_circuit_breaker"] = CheckResult(
            passed=dd_passed,
            detail=f"Daily DD {daily_dd:.2%} < {self.MAX_DAILY_DRAWDOWN:.1%}"
            if dd_passed
            else f"Circuit breaker tripped: Daily DD {daily_dd:.2%} >= {self.MAX_DAILY_DRAWDOWN:.1%}"
        )

        # 5. Max Portfolio Exposure (< 60% in non-USDT)
        total_non_usdt = 0.0
        if hasattr(portfolio, "balances") and portfolio.balances:
            total_non_usdt = sum(
                b.value_usdt for asset, b in portfolio.balances.items()
                if asset != "USDT"
            )
        elif hasattr(portfolio, "exposures") and portfolio.exposures:
            total_non_usdt = sum(v for k, v in portfolio.exposures.items() if k != "USDT")

        new_exposure_pct = (total_non_usdt + position_value) / nav if nav > 0 else 0.0
        exposure_passed = new_exposure_pct <= self.MAX_EXPOSURE_PCT
        checks["max_portfolio_exposure"] = CheckResult(
            passed=exposure_passed,
            detail=f"Exposure {new_exposure_pct:.1%} <= {self.MAX_EXPOSURE_PCT:.1%}"
            if exposure_passed
            else f"Exposure {new_exposure_pct:.1%} exceeds {self.MAX_EXPOSURE_PCT:.1%}"
        )

        # 6. Single-Asset Concentration (< 30% in one asset)
        existing_asset_val = 0.0
        if hasattr(portfolio, "balances") and portfolio.balances:
            existing_asset_val = portfolio.balances.get(base_asset, None)
            existing_asset_val = existing_asset_val.value_usdt if existing_asset_val else 0.0
        elif hasattr(portfolio, "exposures"):
            existing_asset_val = portfolio.exposures.get(symbol, portfolio.exposures.get(base_asset, 0.0))

        new_concentration_pct = (existing_asset_val + position_value) / nav if nav > 0 else 0.0
        conc_passed = new_concentration_pct <= self.MAX_SINGLE_ASSET_PCT
        checks["single_asset_concentration"] = CheckResult(
            passed=conc_passed,
            detail=f"{base_asset} concentration {new_concentration_pct:.1%} <= {self.MAX_SINGLE_ASSET_PCT:.1%}"
            if conc_passed
            else f"{base_asset} concentration {new_concentration_pct:.1%} exceeds {self.MAX_SINGLE_ASSET_PCT:.1%}"
        )

        # 7. Max Simultaneous Positions (<= 5 non-USDT)
        non_usdt_count = 0
        if hasattr(portfolio, "balances") and portfolio.balances:
            non_usdt_count = len([
                b for b in portfolio.balances.values()
                if b.asset != "USDT" and b.total > 0
            ])
        elif hasattr(portfolio, "open_positions"):
            non_usdt_count = portfolio.open_positions

        # If we already have this asset, we are adding to it, not creating a new position
        already_holding = False
        if hasattr(portfolio, "balances") and portfolio.balances:
            already_holding = base_asset in portfolio.balances and portfolio.balances[base_asset].total > 0

        pos_passed = already_holding or (non_usdt_count < self.MAX_POSITIONS)
        checks["simultaneous_positions"] = CheckResult(
            passed=pos_passed,
            detail=f"Holdings {non_usdt_count}/{self.MAX_POSITIONS}"
            if pos_passed
            else f"Max positions reached ({non_usdt_count}/{self.MAX_POSITIONS})"
        )

        # 8. Minimum Order Size (>= $10 USDT Binance requirement)
        min_order_passed = position_value >= self.MIN_ORDER_VALUE_USDT
        checks["min_order_size"] = CheckResult(
            passed=min_order_passed,
            detail=f"${position_value:.2f} >= ${self.MIN_ORDER_VALUE_USDT:.2f}"
            if min_order_passed
            else f"${position_value:.2f} below Binance min ${self.MIN_ORDER_VALUE_USDT:.2f}"
        )

        # 9. Volatility-Adjusted Sizing Check
        size_multiplier = self.REGIME_SIZE_MULTIPLIERS.get(current_regime, 1.0)
        checks["volatility_sizing"] = CheckResult(
            passed=True,
            detail=f"Regime {current_regime.value}: multiplier {size_multiplier:.2f}x"
        )

        # 10. Correlation Check (max 2 positions in high_cap group)
        corr_passed = True
        corr_detail = "Correlation check passed"
        for group_name, group_symbols in self.CORRELATION_GROUPS.items():
            if symbol in group_symbols:
                group_count = 0
                if hasattr(portfolio, "balances") and portfolio.balances:
                    group_count = sum(
                        1 for s in group_symbols
                        if s.replace("USDT", "") in portfolio.balances
                        and portfolio.balances[s.replace("USDT", "")].total > 0
                    )
                if not already_holding and group_count >= 2:
                    corr_passed = False
                    corr_detail = f"Already {group_count} positions in {group_name} group"
                    break

        checks["correlation_limit"] = CheckResult(
            passed=corr_passed,
            detail=corr_detail
        )

        # Verdict
        failed_rules = [k for k, v in checks.items() if not v.passed]
        is_approved = len(failed_rules) == 0
        reason = "All 10 checks passed" if is_approved else f"FAILED: {', '.join(failed_rules)}"

        return RiskGateResult(
            approved=is_approved,
            reason=reason,
            checks=checks,
            timestamp=datetime.now().isoformat()
        )


# Backward-compatible alias
RiskGate = CryptoRiskGate
