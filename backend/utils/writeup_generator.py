from datetime import datetime
from backend.config import settings


def generate_writeup(portfolio, trades) -> str:
    """Generate the one-page hackathon submission write-up from live data."""
    wins = [t for t in trades if getattr(t, "realized_pnl", None) and t.realized_pnl > 0]
    total_closed = len([t for t in trades if str(getattr(t.status, "value", t.status)).upper() in ("CLOSED", "STOPPED_OUT")])
    win_rate = len(wins) / max(total_closed, 1)
    stop_outs = sum(1 for t in trades if str(getattr(t.status, "value", t.status)).upper() == "STOPPED_OUT")
    initial_cap = getattr(settings, "INITIAL_CAPITAL", 10000.0)
    equity = getattr(portfolio, "equity", initial_cap)
    daily_pnl = getattr(portfolio, "daily_pnl", 0.0)
    open_pos = getattr(portfolio, "open_positions", 0)
    regime = getattr(getattr(portfolio, "current_regime", "NORMAL"), "value", "NORMAL")
    total_pnl = getattr(portfolio, "total_pnl", equity - initial_cap)
    total_return_pct = (total_pnl / initial_cap) * 100 if initial_cap > 0 else 0.0
    equity_str = f"${equity:,.2f} USDT"
    pnl_str = f"{daily_pnl:+,.2f} USDT"
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# VolHelix AI - Binance Crypto Autonomous Trading Engine",
        f"> Generated: {ts}",
        "",
        "## Multi-Agent Architecture",
        "7-agent autonomous crypto intelligence with structured debate protocol and 24/7 Position Guardian:",
        "1. **Market Intel Agent** - Binance 24hr tickers, 365-day realized volatility, order book depth, 5-state crypto regime classification",
        "2. **Strategy Synthesizer** - Order Flow market structure (Order Blocks, Fair Value Gaps, Liquidity Heatmap), dynamic TP/SL",
        "3. **Devil's Advocate** - Challenges thesis with adversarial stress-testing, votes AGREE/DISAGREE with strict rationale",
        "4. **Event Scanner** - Protocol hardforks, network upgrades, monthly settlement dates, FOMC & CPI macro monitoring",
        "5. **Consensus Engine** - Weighted multi-agent consensus (deterministic, no LLM hallucinations)",
        "6. **Deterministic Risk Gate** - 10 hard-coded rules (2.5% max capital, 3% daily drawdown breaker, 60% exposure cap, min $10 order)",
        "7. **Execution Agent (BinanceClient)** - Direct spot market order routing on Binance Spot Testnet",
        "8. **24/7 Position Guardian** - Continuous autonomous background monitoring, dynamic take-profit and stop-loss execution",
        "",
        "## Risk Management (Deterministic, Zero LLM)",
        "- Max 2.5% NAV per position | Max 3% daily drawdown circuit breaker (1h halt)",
        "- Dynamic TP/SL derived from institutional market structure invalidation levels",
        f"- {stop_outs} stop-outs triggered to date",
        "",
        "## Performance Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Current Equity | {equity_str} |",
        f"| Initial Capital | ${initial_cap:,.2f} USDT |",
        f"| Total Return | {total_return_pct:+.2f}% |",
        f"| Session PnL | {pnl_str} |",
        f"| Total Trades | {len(trades)} |",
        f"| Closed Trades | {total_closed} |",
        f"| Win Rate | {win_rate:.0%} |",
        f"| Open Positions | {open_pos} |",
        f"| Current Regime | {regime} |",
        "| Trading Session | 24/7/365 Continuous Crypto Spot |",
    ]
    return "\n".join(lines)
