from datetime import datetime


def generate_writeup(portfolio, trades) -> str:
    """Generate the one-page hackathon submission write-up from live data."""
    wins = [t for t in trades if getattr(t, "realized_pnl", None) and t.realized_pnl > 0]
    total_closed = len(trades)
    win_rate = len(wins) / max(total_closed, 1)
    stop_outs = sum(1 for t in trades if str(getattr(t.status, "value", t.status)) == "STOPPED_OUT")
    equity = getattr(portfolio, "equity", 100000)
    daily_pnl = getattr(portfolio, "daily_pnl", 0)
    open_pos = getattr(portfolio, "open_positions", 0)
    regime = getattr(getattr(portfolio, "current_regime", "NORMAL"), "value", "NORMAL")
    total_pnl = getattr(portfolio, "total_pnl", 0)
    total_return_pct = (total_pnl / 100000.0) * 100
    equity_str = "Q{equity:,.2f}".replace("Q", "$").format(equity=equity)
    pnl_str = "Q{daily_pnl:+,.2f}".replace("Q", "$").format(daily_pnl=daily_pnl)
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# VolHelix AI - Hackathon Submission Write-Up",
        f"> Generated: {ts}",
        "",
        "## AI Logic",
        "7-agent autonomous architecture with structured debate protocol:",
        "1. Market Intel Agent - IV Rank/Percentile, 5-state regime classification",
        "2. Strategy Synthesizer - Greeks-optimized options spreads by regime",
        "3. Devil Advocate - challenges thesis, votes AGREE/DISAGREE with reasoning",
        "4. Event Scanner - earnings, FOMC, CPI, news monitoring (parallel)",
        "5. Consensus Engine - weighted 2/3 agreement (deterministic, no LLM)",
        "6. Deterministic Risk Gate - 10 hard-coded rules, ZERO LLM involvement",
        "7. MCP Execution Agent - multi-leg orders via Alpaca MCP Server",
        "",
        "## Risk Management (Deterministic)",
        "- Max 2.5% NAV per position | Max 3% daily drawdown circuit breaker",
        "- Stop-loss at -50% of credit | Take-profit at +60% of max profit",
        f"- {stop_outs} stop-outs triggered to date",
        "",
        "## Performance Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Current Equity | {equity_str} |",
        f"| Total Return | {total_return_pct:+.2f}% |",
        f"| Session PnL | {pnl_str} |",
        f"| Total Trades | {len(trades)} |",
        f"| Win Rate | {win_rate:.0%} |",
        f"| Open Positions | {open_pos} |",
        f"| Current Regime | {regime} |",
    ]
    return "\n".join(lines)
