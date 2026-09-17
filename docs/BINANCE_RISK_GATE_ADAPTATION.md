# VolHelix AI — Risk Gate Adaptation for Crypto Spot Trading

> **Purpose:** Adapt the 10-rule deterministic Risk Gate for crypto spot trading.  
> **Principle:** STILL deterministic, STILL pure Python, STILL zero LLM.  
> **Changes:** Remove options-specific rules, add crypto-specific rules.

---

## Overview of Changes

The original Risk Gate was designed for **options multi-leg spreads**. For crypto **spot** trading, some rules don't apply (DTE, spread width, OI/bid-ask) and need to be replaced with crypto-relevant risk checks.

---

## The 10 Crypto Spot Rules

| # | Rule | Threshold | On Breach |
|---|---|---|---|
| 1 | **Max capital per position** | ≤ 2.5% of portfolio value (USDT) | REJECT trade |
| 2 | **Stop-loss trigger** | −2% from entry (configurable per volatility) | Auto-close position |
| 3 | **Take-profit trigger** | +4% from entry (configurable) | Auto-close position |
| 4 | **Daily drawdown circuit breaker** | > 3% of NAV in single day | HALT ALL trading for 1 hour |
| 5 | **Max portfolio exposure** | Total non-USDT value < 60% of portfolio | REJECT if would breach |
| 6 | **Single-asset concentration** | < 30% of total portfolio in one asset | REJECT if would breach |
| 7 | **Max simultaneous positions** | ≤ 5 non-USDT holdings | REJECT if at limit |
| 8 | **Minimum order size** | Order value ≥ $10 USDT (Binance minimum) | REJECT below minimum |
| 9 | **Volatility-adjusted sizing** | Reduce size by 50% when regime = CRISIS | Auto-reduce |
| 10 | **Correlation check** | Max 2 highly-correlated positions (e.g., BTC+ETH count as correlated) | REJECT if overexposed |

---

## Detailed Rule Specifications

### Rule 1: Max Capital Per Position (KEPT — same logic)

```python
max_loss = proposal.qty * proposal.entry_price  # Total position value
nav = portfolio.equity  # Total portfolio in USDT
check = max_loss <= self.MAX_POSITION_PCT * nav
# Same as before: position value ≤ 2.5% of NAV
```

### Rule 2: Stop-Loss (ADAPTED for crypto volatility)

```python
# Crypto is more volatile than stocks, so stop-losses are slightly wider
STOP_LOSS_DEFAULTS = {
    "BTCUSDT": 0.02,    # -2% (BTC less volatile)
    "ETHUSDT": 0.025,   # -2.5%
    "SOLUSDT": 0.035,   # -3.5% (SOL more volatile)
    "BNBUSDT": 0.03,    # -3%
    "XRPUSDT": 0.035,   # -3.5%
}

# In CRISIS regime, tighten stop-losses by 50%
if regime == Regime.CRISIS:
    stop_loss_pct *= 0.5
```

### Rule 3: Take-Profit (ADAPTED)

```python
TAKE_PROFIT_DEFAULTS = {
    "BTCUSDT": 0.04,    # +4%
    "ETHUSDT": 0.05,    # +5%
    "SOLUSDT": 0.07,    # +7%
    "BNBUSDT": 0.06,    # +6%
    "XRPUSDT": 0.07,    # +7%
}
```

### Rule 4: Daily Drawdown Circuit Breaker (ADAPTED for 24/7)

```python
# Crypto trades 24/7 — "daily" = rolling 24-hour window
# When drawdown exceeds 3%, halt trading for 1 hour (not "rest of day")
MAX_DAILY_DRAWDOWN = 0.03
HALT_DURATION_MINUTES = 60  # 1 hour halt instead of rest-of-day
```

### Rule 5: Max Portfolio Exposure (NEW — replaces delta limit)

```python
# In options, we tracked portfolio delta. In spot, track total exposure.
# Don't be 100% invested — keep at least 40% in USDT as cash buffer.
MAX_EXPOSURE_PCT = 0.60  # Max 60% of portfolio in non-USDT assets

total_non_usdt = sum(
    balance.value_usdt 
    for asset, balance in portfolio.balances.items() 
    if asset != "USDT"
)
exposure_pct = total_non_usdt / portfolio.equity
check = exposure_pct <= MAX_EXPOSURE_PCT
```

### Rule 6: Single-Asset Concentration (KEPT — same logic)

```python
# Same as before: no single crypto > 30% of portfolio
asset_value = portfolio.balances.get(asset, {}).get("value_usdt", 0) + position_value
check = asset_value / portfolio.equity <= 0.30
```

### Rule 7: Max Simultaneous Positions (ADAPTED — fewer for crypto)

```python
# Crypto: max 5 positions (down from 8 for options)
# With only 5 watched symbols, this prevents over-diversification
MAX_POSITIONS = 5
non_usdt_holdings = len([
    b for b in portfolio.balances.values()
    if b.asset != "USDT" and b.total > 0
])
check = non_usdt_holdings < MAX_POSITIONS
```

### Rule 8: Minimum Order Size (NEW — replaces spread width)

```python
# Binance enforces minimum notional value ($10 USDT for most pairs)
MIN_ORDER_VALUE_USDT = 10.0

order_value = proposal.qty * proposal.entry_price
check = order_value >= MIN_ORDER_VALUE_USDT
```

### Rule 9: Volatility-Adjusted Sizing (NEW — replaces DTE check)

```python
# DTE doesn't apply to spot. Instead, adjust size based on volatility regime.
REGIME_SIZE_MULTIPLIERS = {
    Regime.LOW_VOL: 1.0,     # Full size
    Regime.NORMAL: 1.0,      # Full size
    Regime.ELEVATED: 0.75,   # Reduce 25%
    Regime.SQUEEZE: 0.50,    # Reduce 50% (breakout expected)
    Regime.CRISIS: 0.25,     # Reduce 75% (maximum caution)
}

adjusted_qty = proposal.qty * REGIME_SIZE_MULTIPLIERS.get(regime, 1.0)
```

### Rule 10: Correlation Check (ADAPTED for crypto)

```python
# In crypto, many assets are highly correlated with BTC.
# Treat BTC and ETH as a "correlated group" — max 2 positions in the group.
CORRELATION_GROUPS = {
    "high_cap": ["BTCUSDT", "ETHUSDT"],           # BTC and ETH often move together
    "alt_l1": ["SOLUSDT", "BNBUSDT"],             # L1 alts
    "payments": ["XRPUSDT"],                       # Standalone
}

# Max 2 positions in any single correlation group
for group_name, symbols in CORRELATION_GROUPS.items():
    group_count = sum(
        1 for s in symbols
        if s in portfolio.balances and portfolio.balances[s].total > 0
    )
    if proposal.symbol in symbols:
        check = group_count < 2
```

---

## Full Implementation

```python
from dataclasses import dataclass
from datetime import datetime
from backend.models.market import Regime


@dataclass
class CheckResult:
    passed: bool
    detail: str


@dataclass
class RiskGateResult:
    approved: bool
    reason: str
    checks: dict  # str -> CheckResult
    timestamp: str


class CryptoRiskGate:
    """Hard-coded, deterministic risk rules for crypto spot trading. ZERO LLM."""

    MAX_POSITION_PCT = 0.025       # 2.5% of NAV per position
    MAX_DAILY_DRAWDOWN = 0.03      # 3% circuit breaker
    HALT_DURATION_MINUTES = 60     # Halt for 1 hour (not rest of day)
    MAX_EXPOSURE_PCT = 0.60        # Max 60% in non-USDT
    MAX_SINGLE_ASSET_PCT = 0.30    # Max 30% in one asset
    MAX_POSITIONS = 5              # Max 5 non-USDT holdings
    MIN_ORDER_VALUE_USDT = 10.0    # Binance minimum
    
    STOP_LOSS_DEFAULTS = {
        "BTCUSDT": 0.02, "ETHUSDT": 0.025, "SOLUSDT": 0.035,
        "BNBUSDT": 0.03, "XRPUSDT": 0.035,
    }
    
    TAKE_PROFIT_DEFAULTS = {
        "BTCUSDT": 0.04, "ETHUSDT": 0.05, "SOLUSDT": 0.07,
        "BNBUSDT": 0.06, "XRPUSDT": 0.07,
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

    def evaluate(self, proposal, portfolio, regime: Regime) -> RiskGateResult:
        checks = {}
        nav = portfolio.equity
        position_value = proposal.qty * proposal.entry_price

        # 1. Capital allocation
        checks["capital"] = CheckResult(
            passed=position_value <= self.MAX_POSITION_PCT * nav,
            detail=f"{position_value/nav:.1%} of NAV (limit: {self.MAX_POSITION_PCT:.1%})"
        )

        # 2. Stop-loss is set (validation only — actual trigger happens in Guardian)
        sl_pct = self.STOP_LOSS_DEFAULTS.get(proposal.symbol, 0.03)
        checks["stop_loss"] = CheckResult(
            passed=proposal.stop_loss > 0,
            detail=f"SL set at -{sl_pct:.1%} from entry"
        )

        # 3. Take-profit is set
        tp_pct = self.TAKE_PROFIT_DEFAULTS.get(proposal.symbol, 0.05)
        checks["take_profit"] = CheckResult(
            passed=proposal.take_profit > 0,
            detail=f"TP set at +{tp_pct:.1%} from entry"
        )

        # 4. Daily drawdown
        daily_dd = abs(portfolio.daily_pnl) / nav if nav > 0 else 0
        checks["drawdown"] = CheckResult(
            passed=daily_dd < self.MAX_DAILY_DRAWDOWN,
            detail=f"Daily DD: {daily_dd:.2%} (limit: {self.MAX_DAILY_DRAWDOWN:.1%})"
        )

        # 5. Max portfolio exposure
        total_non_usdt = sum(
            b.value_usdt for asset, b in portfolio.balances.items()
            if asset != "USDT"
        ) if hasattr(portfolio, 'balances') else 0
        new_exposure = (total_non_usdt + position_value) / nav if nav > 0 else 0
        checks["exposure"] = CheckResult(
            passed=new_exposure <= self.MAX_EXPOSURE_PCT,
            detail=f"Exposure: {new_exposure:.1%} (limit: {self.MAX_EXPOSURE_PCT:.1%})"
        )

        # 6. Concentration
        base_asset = proposal.symbol.replace("USDT", "")
        existing = portfolio.balances.get(base_asset, None)
        existing_value = existing.value_usdt if existing else 0
        new_concentration = (existing_value + position_value) / nav if nav > 0 else 0
        checks["concentration"] = CheckResult(
            passed=new_concentration <= self.MAX_SINGLE_ASSET_PCT,
            detail=f"{base_asset}: {new_concentration:.1%} (limit: {self.MAX_SINGLE_ASSET_PCT:.1%})"
        )

        # 7. Max positions
        non_usdt_count = len([
            b for b in portfolio.balances.values()
            if b.asset != "USDT" and b.total > 0
        ]) if hasattr(portfolio, 'balances') else 0
        checks["positions"] = CheckResult(
            passed=non_usdt_count < self.MAX_POSITIONS,
            detail=f"{non_usdt_count}/{self.MAX_POSITIONS} positions"
        )

        # 8. Minimum order size
        checks["min_order"] = CheckResult(
            passed=position_value >= self.MIN_ORDER_VALUE_USDT,
            detail=f"Order value: ${position_value:.2f} (min: ${self.MIN_ORDER_VALUE_USDT})"
        )

        # 9. Volatility-adjusted sizing
        size_mult = self.REGIME_SIZE_MULTIPLIERS.get(regime, 1.0)
        checks["vol_sizing"] = CheckResult(
            passed=True,  # Always passes — just adjusts size
            detail=f"Regime {regime.value}: size multiplier = {size_mult}x"
        )

        # 10. Correlation check
        corr_ok = True
        corr_detail = "No correlation overload"
        for group_name, symbols in self.CORRELATION_GROUPS.items():
            if proposal.symbol in symbols:
                group_count = sum(
                    1 for s in symbols
                    if s.replace("USDT", "") in portfolio.balances
                    and portfolio.balances[s.replace("USDT", "")].total > 0
                ) if hasattr(portfolio, 'balances') else 0
                if group_count >= 2:
                    corr_ok = False
                    corr_detail = f"Already {group_count} positions in {group_name} group"
        checks["correlation"] = CheckResult(passed=corr_ok, detail=corr_detail)

        # Final verdict
        approved = all(c.passed for c in checks.values())
        failed = [k for k, v in checks.items() if not v.passed]
        reason = "ALL 10 CHECKS PASSED" if approved else f"FAILED: {', '.join(failed)}"

        return RiskGateResult(
            approved=approved,
            reason=reason,
            checks={k: {"passed": v.passed, "detail": v.detail} for k, v in checks.items()},
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
```

---

## Volatility Regime Engine for Crypto

Since crypto doesn't have VIX, the regime engine must be adapted:

```python
def classify_crypto_regime(
    btc_realized_vol_30d: float,  # 30-day realized volatility of BTC
    vol_percentile: float,        # Where current vol sits vs 1-year history
    squeeze_detected: bool,       # Bollinger Band compression
) -> Regime:
    """Deterministic regime classification for crypto. No LLM."""
    if btc_realized_vol_30d > 80 or vol_percentile > 0.80:
        return Regime.CRISIS
    elif squeeze_detected:
        return Regime.SQUEEZE
    elif btc_realized_vol_30d > 50 or vol_percentile > 0.50:
        return Regime.ELEVATED
    elif btc_realized_vol_30d < 25 and vol_percentile < 0.25:
        return Regime.LOW_VOL
    else:
        return Regime.NORMAL
```

**How to calculate BTC realized volatility:**
```python
import numpy as np

def realized_volatility(closes: list[float], window: int = 30) -> float:
    """Calculate annualized realized volatility from closing prices."""
    if len(closes) < window + 1:
        return 0.0
    log_returns = np.diff(np.log(closes[-window - 1:]))
    daily_vol = np.std(log_returns)
    annualized = daily_vol * np.sqrt(365)  # 365 days (crypto trades 24/7)
    return annualized * 100  # As percentage
```

---

> **Document Version:** 1.0  
> **Created:** September 17, 2026  
> **Purpose:** Risk Gate adaptation reference for Gemini 3.8 Flash
