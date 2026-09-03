# VolHelix AI — Product Requirements Document (PRD)

> **Autonomous Multi-Agent Options & Risk Orchestrator**
> **Challenge:** Options Alpha Agents — Alpaca AI Trading Agents Hackathon 2026
> **Dates:** Aug 28 – Sep 4, 2026 | **Deadline:** Sep 4, 8:30 PM IST | **Prize Pool:** $6,300 | **Enrolled:** 3,439+
> **Hosted by:** LabLab.ai × Alpaca × Featherless

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Hackathon Compliance Matrix](#2-hackathon-compliance-matrix)
3. [Winning Differentiators (Impact Features)](#3-winning-differentiators)
4. [System Architecture](#4-system-architecture)
5. [Agent Specifications](#5-agent-specifications)
6. [Volatility Regime Engine](#6-volatility-regime-engine)
7. [Options Strategy Playbook](#7-options-strategy-playbook)
8. [Deterministic Risk Gate](#8-deterministic-risk-gate)
9. [Dashboard & Judge-Ready UI](#9-dashboard--judge-ready-ui)
10. [Data Models & Schemas](#10-data-models--schemas)
11. [Tech Stack & Dependencies](#11-tech-stack--dependencies)
12. [File & Folder Structure](#12-file--folder-structure)
13. [Alpaca MCP Integration Reference](#13-alpaca-mcp-integration-reference)
14. [Build Execution Plan (5-Day Sprint)](#14-build-execution-plan)
15. [One-Page Write-Up Auto-Generator](#15-one-page-write-up-auto-generator)
16. [Testing & Verification](#16-testing--verification)
17. [Risk Disclosure & Edge Cases](#17-risk-disclosure--edge-cases)

---

## 1. Executive Summary

**VolHelix AI** is an autonomous multi-agent trading system that trades options on Alpaca via the **Model Context Protocol (MCP)**. It uses a dynamic **Volatility-Regime Engine** to classify market conditions in real-time and selects high-probability options strategies (Credit Spreads, Iron Condors, Directional Breakouts) backed by a **deterministic, zero-hallucination Risk Gatekeeper**.

### Why VolHelix Wins

| Judging Pillar | Our Edge |
|---|---|
| **Performance (P&L)** | Regime-adaptive strategy selection maximizes edge; hard risk gate prevents catastrophic loss |
| **Creativity / Engagement** | Multi-agent debate protocol, self-reflective post-trade analysis, real-time reasoning dashboard, 3D vol surface |

### Key Numbers

- **Starting Capital:** \$100,000 (paper account)
- **Max Risk Per Trade:** ≤ 2.5% of NAV (\$2,500 initial)
- **Target Win Rate:** 60–70% on defined-risk spreads
- **Target Sharpe:** > 1.5 over competition period
- **Agent Count:** 7 specialized agents + 1 deterministic risk gate

---

## 2. Hackathon Compliance Matrix

| Requirement | Implementation | Status |
|---|---|---|
| **Autonomous Agent** | 7-agent reasoning loop: Market Scout → Strategy Engine → Devil's Advocate → Consensus → Risk Gate → Executor → Post-Mortem | ✅ |
| **Alpaca MCP / CLI Integration** | All discovery, orders, and position management via Alpaca MCP Server (61+ tools exposed via FastMCP) | ✅ |
| **Options Trading** | Multi-leg options execution (`order_class: mleg`) — Spreads, Iron Condors, Straddles, Greeks-neutral strategies via Alpaca Options API | ✅ |
| **Fresh Paper Account** | Configurable for fresh paper trading account initialized at \$100,000 | ✅ |
| **One-Page Write-Up** | Built-in auto-generator pulls live metrics into architecture & risk-gate markdown document | ✅ |
| **Dedicated Competition Account** | One account per email, isolated paper environment | ✅ |

> [!CAUTION]
> **TWO-ACCOUNT STRATEGY REQUIRED:** Use any paper account for **development & testing**. For **final submission**, create a **brand-new, fresh** Alpaca paper account dedicated to the hackathon. Projects run on existing or reused accounts will **NOT be eligible** for judging. The system must support swapping API keys via `.env` at submission time.

---

## 3. Winning Differentiators

> These are the **8 impact features** that go beyond baseline requirements and will set VolHelix apart from every other submission.

### 3.1 🧠 Multi-Agent Debate & Consensus Protocol

Instead of a single LLM making decisions, VolHelix implements a **structured debate mechanism** between agents:

- The **Market Intel Agent** presents its market thesis (bullish/bearish/neutral + confidence score)
- The **Strategy Agent** proposes 2–3 candidate strategies with expected value calculations
- A **Devil's Advocate Agent** (new) challenges the thesis with counter-arguments and tail risk identification
- Final decision requires **weighted consensus** (minimum 2/3 agreement at ≥ 66% confidence) before passing to Risk Gate
- All debate reasoning is logged and displayed live in the dashboard

> **Why judges love this:** Demonstrates sophisticated AI architecture beyond simple prompt chaining, proves the system resists hallucination-driven bad trades, and mirrors how real hedge fund investment committees operate.

### 3.2 📊 Volatility Regime Classifier (HMM-Based)

Rather than fixed IV thresholds, VolHelix uses a **Hidden Markov Model** to detect 5 market regimes:

| Regime | VIX Range | IV Percentile | Strategy Bias | Position Size |
|---|---|---|---|---|
| 😴 **Low Vol** | < 15 | < 25th | Buy cheap directional plays, calendar spreads | 2.0% NAV |
| 😐 **Normal** | 15–20 | 25th–50th | Balanced: Iron condors, vertical spreads | 2.5% NAV |
| 😰 **Elevated** | 20–30 | 50th–80th | Sell rich premium: Credit spreads, short strangles | 2.0% NAV |
| ⚡ **Squeeze** | BB-detected | Any | Long straddles, debit breakout plays | 1.5% NAV |
| 🔥 **Crisis** | > 30 | > 80th | Defensive: protective puts, reduce all, cash | 1.0% NAV |

> **Why this wins:** Dynamically adapting strategy to regime shows quantitative sophistication. Most competitors will use static if/else rules.

### 3.3 🔄 Self-Reflective Post-Trade Analysis (Learning Loop)

After every closed trade, a **Post-Mortem Agent** runs a structured self-analysis:

1. Compares actual P&L vs. expected value at entry
2. Verifies if the regime classification was correct
3. Scores the strategy selection quality (1–10 scale)
4. Generates explicit lessons learned
5. Feeds refined insights back into the Strategy Agent's context window
6. Maintains a rolling **Strategy Effectiveness Score** per regime

> **Why this wins:** Shows the system learns and improves autonomously — transforms from a static bot into an adaptive learning system.

### 3.4 🎯 Greeks-Optimized Position Sizing (Modified Kelly Criterion)

Instead of flat position sizing, VolHelix uses **Kelly Criterion** with Greeks-aware adjustments:

```
kelly_fraction = (win_rate × avg_win − (1 − win_rate) × avg_loss) / avg_win
position_size = min(kelly_fraction × NAV, max_risk_per_trade)
```

Combined with real-time Greeks management:
- **Delta-neutral portfolio targeting** in elevated vol regime
- **Theta decay harvesting** — prioritize positive-theta strategies in normal/elevated regimes
- **Vega exposure caps** — limit total portfolio vega to prevent vol crush damage
- **Gamma scalping awareness** — reduce near-ATM exposure close to expiry

### 3.5 📡 Real-Time Event Risk Scanner

A background agent that continuously monitors for known catalysts:

- **Earnings dates** for all watched underlyings (SPY, QQQ, AAPL, NVDA, TSLA)
- **FOMC / CPI / NFP dates** — automatically widens stop-losses or reduces size 24h before
- **Options expiration clustering** — detects gamma squeeze risk near monthly OPEX
- **Alpaca News API integration** — real-time news sentiment scoring for watched tickers
- Flags potential risks to the Strategy Agent before trade entry

> **Why this wins:** Shows awareness of real-world market dynamics that pure technical systems miss entirely.

### 3.6 🏆 Live Performance Metrics & Benchmark Comparison

A dashboard module that continuously tracks:

- Real-time equity curve vs. SPY benchmark (using `get_portfolio_history`)
- Rolling Sharpe, Sortino, Max Drawdown, Win Rate, Profit Factor
- Per-strategy performance attribution (which strategies are making money?)
- "Time to target" projections and risk-adjusted returns
- Competition-day performance breakdown

### 3.7 🔐 Full Explainability & Audit Trail (Judge-Ready Transparency)

Every single decision is logged as a structured audit record:

```json
{
  "timestamp": "2026-09-02T14:30:00Z",
  "trade_id": "VH-001",
  "agent_chain": ["market_intel", "strategy", "devils_advocate", "risk_gate", "executor"],
  "regime": "ELEVATED",
  "thesis": "NVDA IV at 85th percentile, expect mean reversion post-earnings",
  "strategy": "bull_put_spread",
  "legs": [
    {"action": "sell", "strike": 120, "type": "put", "expiry": "2026-09-06"},
    {"action": "buy", "strike": 115, "type": "put", "expiry": "2026-09-06"}
  ],
  "risk_gate_result": "APPROVED",
  "risk_checks": {
    "max_capital": "PASS — 1.8% < 2.5%",
    "delta_limit": "PASS — 0.15 < 0.30",
    "concentration": "PASS — portfolio beta 0.4",
    "drawdown": "PASS — daily DD 0.2% < 3.0%"
  },
  "mcp_tool_calls": ["get_option_chain", "get_option_snapshots", "place_order"],
  "debate_summary": "2/3 agents agreed on bullish thesis. Devil's Advocate flagged upcoming FOMC but consensus held since DTE < 5.",
  "confidence": 0.78
}
```

> **Why this wins:** Judges explicitly value "explainable logs of *why* an agent made a specific decision." This is a searchable, exportable, timestamped record of every thought.

### 3.8 🌋 3D Volatility Surface Visualization

A stunning interactive chart showing the options volatility landscape:

- **X-axis:** Strike prices
- **Y-axis:** Expiration dates (DTE)
- **Z-axis:** Implied Volatility
- Color-coded by IV percentile (cool→hot gradient)
- Agent's selected strikes overlaid as glowing markers
- Skew visualization — instantly see term structure and smile

> **Why this wins:** Visually stunning and demonstrates deep institutional-grade options knowledge. Most competitors will have basic line charts.

---

## 4. System Architecture

### 4.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    VOLHELIX AI ORCHESTRATOR                      │
│                  (LangGraph State Machine)                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────┐      │
│  │  1. Market    │   │  2. Strategy │   │  3. Devil's    │      │
│  │  Intel Agent  │──▶│  Synthesizer │◀─▶│  Advocate      │      │
│  │              │   │  Agent       │   │  Agent         │      │
│  └──────┬───────┘   └──────┬───────┘   └────────────────┘      │
│         │                  │                                    │
│  ┌──────┴───────┐   ┌──────┴───────┐                           │
│  │  4. Event    │   │  5. Post-    │                           │
│  │  Risk Scanner│   │  Mortem Agent│                           │
│  └──────────────┘   └──────────────┘                           │
│                          │                                      │
│                    ┌─────┴─────┐                                │
│                    │ CONSENSUS │                                │
│                    │ ENGINE    │ ≥ 66% weighted agreement       │
│                    └─────┬─────┘                                │
│                          ▼                                      │
│              ┌────────────────────────┐                         │
│              │  6. DETERMINISTIC      │  ◀── NO LLM             │
│              │  RISK GATE             │  Pure Python rules       │
│              │  (10 Hard-Coded Rules) │                         │
│              └──────────┬─────────────┘                         │
│                         │ APPROVED / REJECTED                   │
│                         ▼                                       │
│              ┌────────────────────────┐                         │
│              │  7. MCP EXECUTION      │                         │
│              │  AGENT                 │──▶ Alpaca MCP Server    │
│              └────────────────────────┘   (61+ tools via        │
│                                           FastMCP / OpenAPI)    │
├─────────────────────────────────────────────────────────────────┤
│              SHARED STATE (In-Memory + SQLite Persistence)      │
│  Portfolio │ Regime │ Trade Log │ Agent Memory │ Performance    │
└─────────────────────────────────────────────────────────────────┘
                          │
                    ┌─────┴─────┐
                    │ WebSocket │
                    │ (Real-time)│
                    └─────┬─────┘
                          ▼
              ┌────────────────────────┐
              │  NEXT.JS DASHBOARD     │
              │  4 Pages + Live Feed   │
              └────────────────────────┘
```

### 4.2 Data Flow (Per Trading Cycle — Every 5 Minutes During Market Hours)

```
 ──── CYCLE START (scheduler fires every 5 min, 9:30 AM – 4:00 PM ET) ────

 1. MARKET INTEL AGENT (parallel with Event Scanner)
    ├── MCP: get_stock_snapshots() → current prices for SPY, QQQ, AAPL, NVDA, TSLA
    ├── MCP: get_option_chain() → options chains with Greeks and IV
    ├── MCP: get_stock_bars() → 20-day historical for SMA, RSI, Bollinger Bands
    ├── Compute: IV Rank (52-week), IV Percentile (custom calculation)
    ├── Compute: HMM regime classification
    └── Output: MarketSignal { regime, iv_rank, iv_percentile, trend, thesis, candidates[] }

 2. EVENT RISK SCANNER (runs in parallel)
    ├── Check earnings calendar for watched tickers
    ├── Check economic calendar (FOMC, CPI, NFP dates)
    ├── MCP: get_news() → sentiment scoring for watched tickers
    └── Output: RiskFlags { events[], risk_level, size_modifier }

 3. STRATEGY SYNTHESIZER AGENT
    ├── Receives: MarketSignal + RiskFlags + StrategyEffectivenessHistory
    ├── Regime mapping → selects candidate strategy types
    ├── Picks optimal strikes/expiries using Greeks targets
    ├── Calculates expected value, max profit, max loss, breakevens
    └── Output: 2–3 TradeProposal[] with full leg definitions

 4. DEVIL'S ADVOCATE AGENT
    ├── Receives: TradeProposal[] from Strategy Agent
    ├── For each proposal: identify counter-arguments, tail risks, flawed assumptions
    ├── Score each: AGREE/DISAGREE with confidence (0–1) and reasoning
    └── Output: DebateResult { votes[], consensus_score, debate_summary }

 5. CONSENSUS ENGINE (deterministic — not LLM)
    ├── Weighted vote: Strategy Agent (0.4) + Devil's Advocate (0.3) + Market Intel (0.3)
    ├── Threshold: consensus_score ≥ 0.66
    ├── If PASS → forward winning proposal to Risk Gate
    └── If FAIL → log debate, skip cycle, no trade

 6. DETERMINISTIC RISK GATE (NO LLM — pure Python)
    ├── Capital check: max_loss ≤ 2.5% NAV
    ├── Drawdown check: daily DD < 3% → circuit breaker
    ├── Delta check: portfolio delta within bounds
    ├── Concentration check: single underlying < 30%
    ├── Position count check: open positions < 8
    ├── Spread width check: max loss ≤ $2,500
    ├── DTE check: ≥ 3 days to expiry
    ├── Liquidity check: OI > 100, bid-ask spread < 20%
    ├── Buying power check: sufficient margin/cash
    ├── Correlation check: no directional overload
    └── Result: APPROVED (all pass) or REJECTED (with specific failure reasons)

 7. MCP EXECUTION AGENT (if APPROVED)
    ├── MCP: get_account() → verify buying power
    ├── Format multi-leg order payload (OCC symbols, legs[], limit price)
    ├── MCP: place_order(order_class="mleg", ...) → execute trade
    ├── MCP: get_orders() → confirm fill status
    ├── Update portfolio state & position tracking
    ├── Set stop-loss and take-profit monitoring thresholds
    └── Log full audit trail (every MCP request + response)

 8. EXIT MONITOR (continuous background)
    ├── MCP: get_positions() → check all open positions
    ├── For each position: check P&L vs stop-loss (-50% credit) and take-profit (+60% max)
    ├── If triggered: MCP: close_position() → exit trade
    └── On close: trigger Post-Mortem Agent

 9. POST-MORTEM AGENT (on trade close)
    ├── Compare actual P&L vs expected value at entry
    ├── Verify regime classification accuracy
    ├── Score strategy selection (1–10)
    ├── Generate explicit lessons learned
    ├── Update StrategyEffectiveness scores (rolling window)
    └── Feed refined insights into Strategy Agent's context

 ──── CYCLE END (results pushed to dashboard via WebSocket) ────
```

---

## 5. Agent Specifications

### 5.1 Market Intel Agent

| Field | Detail |
|---|---|
| **Trigger** | Every 5 min during market hours (9:30 AM – 4:00 PM ET) |
| **MCP Tools Used** | `get_stock_snapshots`, `get_option_chain`, `get_option_snapshots`, `get_stock_bars`, `get_latest_index_values` (VIX) |
| **Underlyings** | SPY, QQQ, AAPL, NVDA, TSLA (configurable in `config.py`) |
| **Computations** | IV Rank (52-week), IV Percentile, RSI(14), 20-day SMA trend, Bollinger Band width, squeeze detection |
| **Output** | `MarketSignal` — regime classification, thesis, confidence, candidates |
| **LLM Role** | Synthesize multi-indicator signals into a coherent market thesis string |

### 5.2 Strategy Synthesizer Agent

| Field | Detail |
|---|---|
| **Trigger** | Receives `MarketSignal` from Market Intel |
| **Inputs** | MarketSignal, current portfolio state, RiskFlags, strategy effectiveness history |
| **Strategy Selection** | Rule-based regime → strategy-type mapping, then LLM refinement for strike/expiry |
| **Output** | 2–3 `TradeProposal` objects with full leg definitions, Greeks profiles, expected values |
| **Greeks Targets** | Delta: 0.15–0.30 (directional), < 0.10 (neutral) · Theta: positive preferred · DTE: 7–45 days |

### 5.3 Devil's Advocate Agent

| Field | Detail |
|---|---|
| **Trigger** | Receives `TradeProposal[]` from Strategy Agent |
| **Prompt Role** | "You are a skeptical risk analyst. Your job is to find flaws, tail risks, and reasons NOT to take this trade." |
| **Analysis** | Counter-arguments, catalyst risks, historical failure patterns, assumption testing |
| **Output** | `DebateResult` with per-proposal votes (AGREE/DISAGREE), confidence (0–1), counter_arguments[] |
| **Decision Rule** | Trade proceeds only if weighted consensus ≥ 66% |

### 5.4 Event Risk Scanner

| Field | Detail |
|---|---|
| **Trigger** | Runs in parallel with Market Intel (every 5 min) |
| **Data Sources** | Alpaca `get_news`, `get_calendar`, `get_clock`, economic calendar (hardcoded key dates + API) |
| **Output** | `RiskFlags` — event list, aggregate risk level, position size modifier |
| **Actions** | Can reduce position sizing by 50% pre-event, or block trades entirely during crisis events |

### 5.5 Deterministic Risk Gate (NO LLM)

See [Section 8](#8-deterministic-risk-gate) for full specification.

### 5.6 MCP Execution Agent

| MCP Tool | Usage |
|---|---|
| `get_account` | Check buying power, equity, margin before trade |
| `get_option_chain` | Discover available contracts for target underlying |
| `get_option_snapshots` | Current price, Greeks, IV for specific contracts |
| `place_order` | Execute multi-leg options order (`order_class: mleg`) |
| `get_orders` | Confirm fill status, detect partial fills |
| `get_positions` | Monitor all open positions for exit triggers |
| `close_position` | Execute stop-loss / take-profit exits |
| `get_portfolio_history` | Feed dashboard equity curve data |
| `exercise_options_position` | Handle early exercise scenarios if needed |

### 5.7 Post-Mortem Agent

| Field | Detail |
|---|---|
| **Trigger** | When a position is closed (filled exit order detected) |
| **Analysis** | Actual P&L vs expected, regime accuracy check, strategy quality score (1–10) |
| **Output** | `PostMortem` record + updated per-strategy rolling effectiveness scores |
| **Feedback Loop** | Top 5 most recent lessons injected into Strategy Agent's system prompt context |

---

## 6. Volatility Regime Engine

### 6.1 Core Metrics (Computed Internally — Alpaca Does NOT Provide IV Rank)

```python
# ── IV Rank (52-week) ──
# Alpaca provides current IV per contract; we must compute rank ourselves
iv_rank = (current_iv - iv_52w_low) / (iv_52w_high - iv_52w_low)

# ── IV Percentile ──
# What percentage of trading days in the past year had a lower IV
iv_percentile = count(historical_ivs < current_iv) / len(historical_ivs)

# ── VIX Squeeze Detection (Bollinger Band method) ──
vix_bb_width = (upper_bb - lower_bb) / middle_bb
squeeze = vix_bb_width < 0.10  # Tight compression = breakout imminent

# ── Trend Detection ──
sma_20 = ta.sma(close, 20)
trend = "BULLISH" if close > sma_20 else "BEARISH"
rsi_14 = ta.rsi(close, 14)
```

### 6.2 Regime Classification

```python
from enum import Enum

class Regime(str, Enum):
    LOW_VOL = "LOW_VOL"
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    SQUEEZE = "SQUEEZE"
    CRISIS = "CRISIS"

def classify_regime(vix: float, iv_percentile: float, squeeze: bool) -> Regime:
    """Deterministic regime classification. No LLM."""
    if vix > 30 or iv_percentile > 0.80:
        return Regime.CRISIS
    elif squeeze:
        return Regime.SQUEEZE  # Bollinger squeeze → expect violent breakout
    elif vix > 20 or iv_percentile > 0.50:
        return Regime.ELEVATED
    elif vix < 15 and iv_percentile < 0.25:
        return Regime.LOW_VOL
    else:
        return Regime.NORMAL
```

### 6.3 Strategy Mapping by Regime

| Regime | Primary Strategies | Size | DTE | Theta Target |
|---|---|---|---|---|
| **LOW_VOL** | Long calls/puts, Calendar spreads, Debit spreads | 2.0% NAV | 21–45 | Neutral |
| **NORMAL** | Iron condors, Vertical spreads (credit & debit) | 2.5% NAV | 14–30 | Positive |
| **ELEVATED** | Credit spreads (sell rich premium), Short strangles | 2.0% NAV | 7–21 | Positive |
| **SQUEEZE** | Long straddles, Debit spreads (breakout) | 1.5% NAV | 7–14 | Negative (ok) |
| **CRISIS** | Protective puts only, Reduce all positions, Hold cash | 1.0% NAV | N/A | N/A |

---

## 7. Options Strategy Playbook

### 7.1 Bull Put Spread (Credit — Bullish Bias)

```
Sell 1 Put @ Strike A  (closer to ATM, higher premium)
Buy 1 Put @ Strike B   (further OTM, B < A, protection)

Max Profit  = Net Credit Received
Max Loss    = (A − B) − Net Credit
Breakeven   = A − Net Credit
```

**Entry:** Bullish thesis · IV Percentile > 50 · RSI > 40 · ELEVATED or NORMAL regime

### 7.2 Bear Call Spread (Credit — Bearish Bias)

```
Sell 1 Call @ Strike A  (closer to ATM)
Buy 1 Call @ Strike B   (further OTM, B > A)

Max Profit  = Net Credit Received
Max Loss    = (B − A) − Net Credit
```

**Entry:** Bearish thesis · IV Percentile > 50 · RSI < 60 · ELEVATED or NORMAL regime

### 7.3 Iron Condor (Credit — Neutral)

```
Sell 1 Put  @ Strike A   ← lower short put
Buy 1 Put  @ Strike B   ← lower long put (B < A)
Sell 1 Call @ Strike C   ← upper short call
Buy 1 Call @ Strike D   ← upper long call (D > C)

Max Profit  = Total Net Credit (both spreads combined)
Max Loss    = Wider spread width − Net Credit
```

**Entry:** Neutral thesis · NORMAL regime · IV Rank > 40% · Low recent movement

### 7.4 Long Straddle (Debit — Breakout)

```
Buy 1 Call @ ATM Strike
Buy 1 Put  @ ATM Strike  (same expiry)

Max Profit  = Unlimited (either direction)
Max Loss    = Total Debit Paid
```

**Entry:** SQUEEZE regime detected · Pre-major-event · IV Percentile < 30

### 7.5 Calendar Spread (Horizontal — Vol Expansion)

```
Sell 1 Option @ Near-term expiry   (faster theta decay)
Buy 1 Option @ Further-term expiry  (same strike, slower decay)

Profits from: Theta decay differential + IV expansion in back month
```

**Entry:** LOW_VOL regime · Expect IV to rise · Stable/range-bound underlying

---

## 8. Deterministic Risk Gate

> **CRITICAL: This is a pure Python module with ZERO LLM involvement.** Every rule is hard-coded and deterministic.

### 8.1 The 10 Rules

| # | Rule | Threshold | On Breach |
|---|---|---|---|
| 1 | **Max capital per position** | ≤ 2.5% of NAV | REJECT trade |
| 2 | **Stop-loss trigger** | −50% of credit received | Auto-close via MCP |
| 3 | **Take-profit trigger** | +50% to +70% of max profit | Auto-close via MCP |
| 4 | **Daily drawdown circuit breaker** | > 3% of NAV in single day | HALT ALL trading for remainder of day |
| 5 | **Max portfolio delta** | \|Δ\| < 0.50 per \$10k NAV | REJECT if would breach |
| 6 | **Single-underlying concentration** | < 30% of total capital | REJECT if would breach |
| 7 | **Max simultaneous positions** | ≤ 8 open positions | REJECT if at limit |
| 8 | **Spread width limit** | Max loss ≤ \$2,500 per spread | REJECT if exceeds |
| 9 | **Minimum DTE** | ≥ 3 days to expiration | REJECT 0–2 DTE trades |
| 10 | **Liquidity check** | OI > 100 & bid-ask spread < 20% of mid | REJECT illiquid contracts |

### 8.2 Implementation

```python
from dataclasses import dataclass

@dataclass
class CheckResult:
    passed: bool
    detail: str

@dataclass
class RiskGateResult:
    approved: bool
    reason: str
    checks: dict[str, CheckResult]
    timestamp: str

class RiskGate:
    """Hard-coded, deterministic risk rules. ZERO LLM involvement."""

    MAX_POSITION_PCT = 0.025       # 2.5% of NAV
    MAX_DAILY_DRAWDOWN = 0.03      # 3% circuit breaker
    MAX_PORTFOLIO_DELTA = 0.50     # per $10k NAV
    MAX_SINGLE_UNDERLYING = 0.30   # 30% concentration
    MAX_POSITIONS = 8
    MAX_SPREAD_LOSS = 2500         # dollars
    MIN_DTE = 3
    MIN_OPEN_INTEREST = 100
    MAX_BID_ASK_SPREAD_PCT = 0.20
    STOP_LOSS_PCT = -0.50          # -50% of credit
    TAKE_PROFIT_PCT = 0.60         # +60% of max profit

    def evaluate(self, proposal: "TradeProposal", portfolio: "Portfolio") -> RiskGateResult:
        checks = {}

        # 1. Capital allocation
        max_loss = proposal.calculate_max_loss()
        nav = portfolio.total_equity
        checks["capital"] = CheckResult(
            passed=max_loss <= self.MAX_POSITION_PCT * nav,
            detail=f"{max_loss/nav:.1%} of NAV (limit: {self.MAX_POSITION_PCT:.1%})"
        )

        # 2. Daily drawdown circuit breaker
        checks["drawdown"] = CheckResult(
            passed=abs(portfolio.daily_pnl) / nav < self.MAX_DAILY_DRAWDOWN,
            detail=f"Daily DD: {portfolio.daily_pnl/nav:.2%} (limit: {self.MAX_DAILY_DRAWDOWN:.1%})"
        )

        # 3. Portfolio delta
        new_delta = portfolio.total_delta + proposal.net_delta
        delta_limit = self.MAX_PORTFOLIO_DELTA * (nav / 10_000)
        checks["delta"] = CheckResult(
            passed=abs(new_delta) <= delta_limit,
            detail=f"Portfolio Δ: {new_delta:.2f} (limit: ±{delta_limit:.2f})"
        )

        # 4. Concentration
        exposure = portfolio.exposure_by_underlying.get(proposal.underlying, 0) + max_loss
        checks["concentration"] = CheckResult(
            passed=exposure / nav <= self.MAX_SINGLE_UNDERLYING,
            detail=f"{proposal.underlying}: {exposure/nav:.1%} (limit: {self.MAX_SINGLE_UNDERLYING:.1%})"
        )

        # 5. Max positions
        checks["positions"] = CheckResult(
            passed=portfolio.open_position_count < self.MAX_POSITIONS,
            detail=f"{portfolio.open_position_count}/{self.MAX_POSITIONS} positions"
        )

        # 6. Spread width / max loss
        checks["spread_width"] = CheckResult(
            passed=max_loss <= self.MAX_SPREAD_LOSS,
            detail=f"Max loss: ${max_loss:.0f} (limit: ${self.MAX_SPREAD_LOSS})"
        )

        # 7. DTE
        checks["dte"] = CheckResult(
            passed=proposal.dte >= self.MIN_DTE,
            detail=f"DTE: {proposal.dte} (min: {self.MIN_DTE})"
        )

        # 8. Liquidity
        all_liquid = all(
            leg.open_interest >= self.MIN_OPEN_INTEREST
            and (leg.ask - leg.bid) / ((leg.ask + leg.bid) / 2) <= self.MAX_BID_ASK_SPREAD_PCT
            for leg in proposal.legs
        )
        checks["liquidity"] = CheckResult(
            passed=all_liquid,
            detail="All legs meet OI & bid-ask requirements" if all_liquid else "Illiquid leg detected"
        )

        # 9. Buying power
        checks["buying_power"] = CheckResult(
            passed=portfolio.buying_power >= max_loss,
            detail=f"Buying power: ${portfolio.buying_power:,.0f} (need: ${max_loss:,.0f})"
        )

        # 10. Correlation / directional overload
        same_direction_count = sum(
            1 for t in portfolio.positions
            if t.proposal.underlying == proposal.underlying
            and t.status == "OPEN"
        )
        checks["correlation"] = CheckResult(
            passed=same_direction_count < 2,
            detail=f"{same_direction_count} existing {proposal.underlying} positions (max: 2)"
        )

        approved = all(c.passed for c in checks.values())
        failed = [k for k, v in checks.items() if not v.passed]
        reason = "ALL 10 CHECKS PASSED" if approved else f"FAILED: {', '.join(failed)}"

        return RiskGateResult(
            approved=approved,
            reason=reason,
            checks=checks,
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
```

---

## 9. Dashboard & Judge-Ready UI

### 9.1 Technology

| Layer | Choice |
|---|---|
| **Framework** | Next.js 14 (App Router) + TypeScript |
| **Styling** | Tailwind CSS + shadcn/ui components (dark theme, glassmorphism cards) |
| **Real-time** | Socket.IO (WebSocket) for live push updates |
| **Charts** | Recharts (equity curve, bar charts), Lightweight Charts (TradingView price), Plotly.js (3D vol surface) |
| **Icons** | Lucide React |

### 9.2 Page Layouts

#### Page 1: Command Center (`/`)

```
┌──────────────────────────────────────────────────────────────────┐
│  VolHelix AI — Command Center                     [LIVE] 🟢     │
├──────────┬───────────┬──────────┬──────────┬─────────────────────┤
│ Equity   │ Daily P&L │ Win Rate │ Sharpe   │ Current Regime      │
│$102,450  │ +$1,230   │ 67%      │ 1.82     │ 😰 ELEVATED         │
│ +2.45%   │ +1.21%    │ 8/12     │          │ IV%: 72 · VIX: 24   │
├──────────┴───────────┴──────────┴──────────┴─────────────────────┤
│                                                                  │
│  📈 Equity Curve vs SPY Benchmark                                │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  [Recharts line chart — VolHelix (green) vs SPY (gray)]   │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│  📊 Active Positions                                             │
│  ┌──────┬───────────┬──────────┬─────┬───────┬───────┬────────┐ │
│  │Ticker│ Strategy  │ Strikes  │ DTE │ Delta │  P&L  │ Status │ │
│  ├──────┼───────────┼──────────┼─────┼───────┼───────┼────────┤ │
│  │ NVDA │ Bull Put  │ 120/115  │  4  │ +0.15 │ +$85  │  OPEN  │ │
│  │ SPY  │ Iron Cond │ 540-560  │  12 │ -0.02 │ +$42  │  OPEN  │ │
│  │ AAPL │ Bear Call │ 230/235  │  8  │ -0.18 │ -$15  │  OPEN  │ │
│  └──────┴───────────┴──────────┴─────┴───────┴───────┴────────┘ │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│  🧠 Live Agent Reasoning Feed                                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ 14:30 [MARKET_INTEL] NVDA IV Rank: 82%. Regime: ELEVATED. │  │
│  │       Thesis: Bearish bias, expect mean reversion in vol.  │  │
│  │ 14:30 [STRATEGY] Proposing: Bull Put 120/115, 4 DTE,      │  │
│  │       credit $1.25, EV +$0.45                              │  │
│  │ 14:30 [DEVIL_ADV] AGREE (0.72). Minor concern: FOMC in    │  │
│  │       5 days but outside our DTE window. Risk acceptable.  │  │
│  │ 14:31 [RISK_GATE] ✅ APPROVED — all 10 checks passed.     │  │
│  │       Capital: 1.8% < 2.5%. Delta: 0.15 < 0.30.           │  │
│  │ 14:31 [EXECUTOR] MCP→place_order() filled @ $1.22 credit  │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

#### Page 2: Volatility Lab (`/volatility`)

- **3D Volatility Surface** (Plotly.js) — interactive rotate/zoom
- **IV Rank / IV Percentile gauges** per underlying (radial gauges)
- **Regime History Timeline** — horizontal color-coded bar showing regime transitions over time
- **Portfolio Greeks Heatmap** — aggregate delta, theta, vega, gamma exposure with limits visualized

#### Page 3: Trade History & Analytics (`/history`)

- Full trade log table (sortable, filterable by ticker/strategy/regime/outcome)
- Strategy performance breakdown: win rate + avg P&L grouped by strategy type
- Regime accuracy tracker: was the classification correct? (pie chart)
- Cumulative P&L by strategy type (stacked area chart)
- Per-trade P&L waterfall chart

#### Page 4: Audit Trail (`/audit`)

- Searchable, scrollable log of every agent decision
- JSON tree viewer for full trade audit objects (collapsible)
- MCP tool call history with request/response payloads
- Export to markdown button (generates ONE_PAGER.md)

---

## 10. Data Models & Schemas

### 10.1 Python (Pydantic) — Backend

```python
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

# ── Enums ──
class Regime(str, Enum):
    LOW_VOL = "LOW_VOL"
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    SQUEEZE = "SQUEEZE"
    CRISIS = "CRISIS"

class Trend(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

class StrategyType(str, Enum):
    BULL_PUT_SPREAD = "bull_put_spread"
    BEAR_CALL_SPREAD = "bear_call_spread"
    IRON_CONDOR = "iron_condor"
    LONG_STRADDLE = "long_straddle"
    CALENDAR_SPREAD = "calendar_spread"
    PROTECTIVE_PUT = "protective_put"
    COVERED_CALL = "covered_call"

class TradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    STOPPED_OUT = "STOPPED_OUT"
    TAKE_PROFIT = "TAKE_PROFIT"

# ── Core Models ──
class OptionLeg(BaseModel):
    action: str                 # "buy" or "sell"
    contract_type: str          # "call" or "put"
    strike: float
    expiry: str                 # YYYY-MM-DD
    quantity: int = 1
    symbol: str                 # OCC symbol, e.g. NVDA260906P00120000
    premium: float
    delta: float
    theta: float
    vega: float
    gamma: float
    open_interest: int
    bid: float
    ask: float

class MarketSignal(BaseModel):
    timestamp: datetime
    underlying: str
    price: float
    iv_current: float
    iv_rank: float              # 0–1
    iv_percentile: float        # 0–1
    regime: Regime
    trend: Trend
    rsi_14: float
    sma_20_trend: str           # "ABOVE" or "BELOW"
    bb_squeeze: bool
    thesis: str                 # LLM-generated natural language
    confidence: float           # 0–1

class TradeProposal(BaseModel):
    id: str
    underlying: str
    strategy_type: StrategyType
    legs: list[OptionLeg]
    net_credit_debit: float     # positive = credit
    max_profit: float
    max_loss: float
    breakeven: list[float]
    net_delta: float
    net_theta: float
    net_vega: float
    net_gamma: float
    dte: int
    expected_value: float
    regime_at_entry: Regime
    thesis: str
    confidence: float

    def calculate_max_loss(self) -> float:
        return abs(self.max_loss)

class RiskFlags(BaseModel):
    events: list[dict]          # { "type": "earnings", "ticker": "NVDA", "date": "..." }
    risk_level: str             # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    size_modifier: float = 1.0  # 0.5 = reduce size by 50%

class AgentVote(BaseModel):
    agent: str
    vote: str                   # "AGREE" or "DISAGREE"
    confidence: float
    reasoning: str
    counter_arguments: list[str] = []

class DebateResult(BaseModel):
    proposal_id: str
    votes: list[AgentVote]
    consensus_reached: bool
    consensus_score: float      # 0–1
    winning_proposal_id: str | None
    debate_summary: str

class CheckResult(BaseModel):
    passed: bool
    detail: str

class RiskGateResult(BaseModel):
    approved: bool
    reason: str
    checks: dict[str, CheckResult]
    timestamp: str

class MCPCallLog(BaseModel):
    tool: str
    request: dict
    response: dict
    timestamp: str
    duration_ms: int

class PostMortem(BaseModel):
    trade_id: str
    actual_pnl: float
    expected_pnl: float
    pnl_diff: float
    regime_was_correct: bool
    strategy_score: int         # 1–10
    lessons: list[str]
    timestamp: str

class TradeRecord(BaseModel):
    trade_id: str
    timestamp_opened: str
    timestamp_closed: str | None = None
    status: TradeStatus
    proposal: TradeProposal
    risk_gate_result: RiskGateResult
    debate_result: DebateResult
    mcp_calls: list[MCPCallLog] = []
    fill_price: float | None = None
    current_pnl: float = 0.0
    realized_pnl: float | None = None
    post_mortem: PostMortem | None = None

class PortfolioSnapshot(BaseModel):
    timestamp: str
    total_equity: float
    buying_power: float
    daily_pnl: float
    daily_pnl_pct: float
    total_pnl: float
    total_pnl_pct: float
    open_position_count: int
    total_delta: float
    total_theta: float
    total_vega: float
    exposure_by_underlying: dict[str, float]
    current_regime: Regime
```

### 10.2 TypeScript — Frontend (mirrors backend models in `lib/types.ts`)

```typescript
// Matches Python Pydantic models exactly for type-safe API communication
export type Regime = "LOW_VOL" | "NORMAL" | "ELEVATED" | "SQUEEZE" | "CRISIS";
export type Trend = "BULLISH" | "BEARISH" | "NEUTRAL";
export type StrategyType =
  | "bull_put_spread" | "bear_call_spread" | "iron_condor"
  | "long_straddle" | "calendar_spread" | "protective_put" | "covered_call";
export type TradeStatus = "OPEN" | "CLOSED" | "STOPPED_OUT" | "TAKE_PROFIT";

export interface MarketSignal {
  timestamp: string;
  underlying: string;
  price: number;
  iv_current: number;
  iv_rank: number;
  iv_percentile: number;
  regime: Regime;
  trend: Trend;
  rsi_14: number;
  sma_20_trend: "ABOVE" | "BELOW";
  bb_squeeze: boolean;
  thesis: string;
  confidence: number;
}

// ... (remaining interfaces mirror Python models identically)
```

---

## 11. Tech Stack & Dependencies

### 11.1 Backend (Python 3.11+)

| Package | Purpose | Version |
|---|---|---|
| `alpaca-py` | Alpaca SDK — market data & trading | latest |
| `alpaca-mcp-server` | MCP server for AI-agent integration | latest |
| `langgraph` | Agent orchestration & state machine | 0.2+ |
| `langchain-google-genai` | LLM provider — Google Gemini (FREE tier) | latest |
| `google-genai` | Google Gemini SDK (gemini-2.5-flash — free) | latest |
| `numpy` | Numerical computations | 1.26+ |
| `pandas` | Data manipulation, IV history, rolling calcs | 2.2+ |
| `scipy` | Black-Scholes, statistical functions | 1.12+ |
| `hmmlearn` | Hidden Markov Model for regime detection | 0.3+ |
| `fastapi` | REST API backend for dashboard | 0.110+ |
| `uvicorn` | ASGI server | 0.27+ |
| `python-socketio` | WebSocket for real-time dashboard updates | 5.10+ |
| `pydantic` | Data validation & serialization | 2.6+ |
| `apscheduler` | Cron-like scheduling for trading cycles | 3.10+ |
| `python-dotenv` | Environment variable management | 1.0+ |
| `loguru` | Structured, colored logging | 0.7+ |
| `aiosqlite` | Async SQLite for trade log persistence | 0.20+ |
| `httpx` | Async HTTP client for external APIs | 0.27+ |

### 11.2 Frontend (Node.js 20+)

| Package | Purpose |
|---|---|
| `next` (14+) | React framework with App Router |
| `typescript` | Type safety |
| `tailwindcss` (3.4+) | Utility-first CSS |
| `@shadcn/ui` | Prebuilt component library |
| `recharts` | Equity curve, bar charts, pie charts |
| `lightweight-charts` | TradingView-style price charts |
| `plotly.js` + `react-plotly.js` | 3D volatility surface |
| `socket.io-client` | Real-time WebSocket connection |
| `lucide-react` | Icons |
| `date-fns` | Date formatting & manipulation |
| `clsx` + `tailwind-merge` | Conditional class merging |

### 11.3 Infrastructure

| Tool | Purpose |
|---|---|
| Docker + Docker Compose | One-command full-stack deployment |
| `.env` file | API keys (`ALPACA_API_KEY`, `ALPACA_API_SECRET`, `GOOGLE_API_KEY`) |
| SQLite | Trade log & regime history persistence (zero-config) |
| JSON files | IV history cache (daily snapshots) |

---

## 12. File & Folder Structure

```
VolHelix-AI/
├── README.md                           # Quick start, setup instructions
├── PRD.md                              # This document
├── ONE_PAGER.md                        # Auto-generated hackathon submission write-up
├── docker-compose.yml                  # Full stack: backend + frontend + MCP
├── .env.example                        # Template for API keys
├── .gitignore
│
├── backend/                            # Python backend
│   ├── main.py                         # FastAPI app entrypoint + Socket.IO mount
│   ├── config.py                       # Settings, env vars, constants
│   ├── scheduler.py                    # APScheduler — 5-min trading loop
│   │
│   ├── agents/                         # ── Multi-Agent System ──
│   │   ├── __init__.py
│   │   ├── orchestrator.py             # LangGraph state machine (full pipeline)
│   │   ├── market_intel.py             # Agent 1: Market scanning & regime detection
│   │   ├── strategy_synthesizer.py     # Agent 2: Options strategy design
│   │   ├── devils_advocate.py          # Agent 3: Debate & counter-arguments
│   │   ├── event_scanner.py            # Agent 4: Catalyst & event risk monitor
│   │   ├── executor.py                 # Agent 5: MCP execution & order management
│   │   ├── post_mortem.py              # Agent 6: Self-reflective trade analysis
│   │   └── consensus.py               # Consensus engine (weighted voting, deterministic)
│   │
│   ├── engine/                         # ── Core Computation Engine ──
│   │   ├── __init__.py
│   │   ├── regime.py                   # Volatility regime classifier (HMM + rules)
│   │   ├── greeks.py                   # Black-Scholes Greeks calculator
│   │   ├── iv_calculator.py            # IV Rank, IV Percentile (custom — Alpaca doesn't provide)
│   │   ├── position_sizer.py           # Modified Kelly Criterion + regime-adjusted sizing
│   │   ├── strategy_builder.py         # Options strategy leg construction
│   │   └── indicators.py              # RSI, SMA, Bollinger Bands, squeeze detection
│   │
│   ├── risk/                           # ── Deterministic Risk Gate ──
│   │   ├── __init__.py
│   │   ├── risk_gate.py                # 10 hard-coded rules (ZERO LLM)
│   │   ├── circuit_breaker.py          # Daily drawdown halt mechanism
│   │   └── exit_manager.py             # Stop-loss & take-profit monitor (background)
│   │
│   ├── mcp/                            # ── Alpaca MCP Integration ──
│   │   ├── __init__.py
│   │   ├── client.py                   # MCP client wrapper (connect, call tools)
│   │   └── tools.py                    # Tool call formatters & response parsers
│   │
│   ├── models/                         # ── Pydantic Data Models ──
│   │   ├── __init__.py
│   │   ├── market.py                   # MarketSignal, OptionLeg, RiskFlags
│   │   ├── trade.py                    # TradeProposal, TradeRecord, MCPCallLog
│   │   ├── risk.py                     # RiskGateResult, CheckResult
│   │   ├── portfolio.py                # PortfolioSnapshot, Portfolio
│   │   └── debate.py                   # DebateResult, AgentVote, PostMortem
│   │
│   ├── store/                          # ── State Management ──
│   │   ├── __init__.py
│   │   ├── portfolio_store.py          # In-memory portfolio state + snapshots
│   │   ├── trade_log.py                # SQLite persistence for trade records
│   │   ├── regime_history.py           # Regime transition history
│   │   └── iv_history.py              # IV data cache for IV Rank/Percentile calcs
│   │
│   ├── api/                            # ── REST & WebSocket API ──
│   │   ├── __init__.py
│   │   ├── routes.py                   # GET endpoints: /portfolio, /trades, /signals, /audit
│   │   └── websocket.py               # Socket.IO: emit portfolio updates, reasoning feed
│   │
│   ├── utils/                          # ── Utilities ──
│   │   ├── __init__.py
│   │   ├── logger.py                   # Loguru configuration (file + console + structured)
│   │   ├── writeup_generator.py        # Auto-generate ONE_PAGER.md from live data
│   │   └── calendar.py                 # Economic calendar, earnings dates, market hours
│   │
│   ├── data/                           # ── Persisted Data ──
│   │   ├── trades.db                   # SQLite trade log (auto-created)
│   │   ├── iv_history/                 # Daily IV snapshots (JSON files per ticker)
│   │   └── regime_log.jsonl            # Regime transition log
│   │
│   ├── tests/                          # ── Test Suite ──
│   │   ├── __init__.py
│   │   ├── test_risk_gate.py           # All 10 rules + edge cases
│   │   ├── test_regime.py              # Regime classification boundaries
│   │   ├── test_strategy_builder.py    # Strategy leg construction
│   │   ├── test_position_sizer.py      # Kelly Criterion calculations
│   │   ├── test_iv_calculator.py       # IV Rank / Percentile
│   │   ├── test_consensus.py           # Weighted voting logic
│   │   └── conftest.py                 # Shared fixtures
│   │
│   ├── pyproject.toml                  # Python project config
│   ├── requirements.txt                # Pip dependencies
│   └── Dockerfile
│
├── frontend/                           # ── Next.js Dashboard ──
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── next.config.mjs
│   ├── Dockerfile
│   │
│   ├── app/                            # App Router pages
│   │   ├── layout.tsx                  # Root layout — sidebar + dark theme
│   │   ├── page.tsx                    # Page 1: Command Center
│   │   ├── volatility/
│   │   │   └── page.tsx                # Page 2: Volatility Lab
│   │   ├── history/
│   │   │   └── page.tsx                # Page 3: Trade History & Analytics
│   │   ├── audit/
│   │   │   └── page.tsx                # Page 4: Audit Trail
│   │   └── globals.css                 # Tailwind base + custom styles
│   │
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx             # Navigation sidebar with regime indicator
│   │   │   └── Header.tsx              # Top bar with live status + clock
│   │   ├── dashboard/
│   │   │   ├── MetricCards.tsx          # Equity, P&L, Win Rate, Sharpe, Regime
│   │   │   ├── EquityCurve.tsx         # Recharts — VolHelix vs SPY
│   │   │   ├── PositionsTable.tsx      # Active positions with Greeks
│   │   │   └── ReasoningFeed.tsx       # Live agent thought stream
│   │   ├── volatility/
│   │   │   ├── VolSurface3D.tsx        # Plotly 3D volatility surface
│   │   │   ├── IVGauges.tsx            # IV Rank/Percentile radial gauges
│   │   │   ├── RegimeTimeline.tsx      # Color-coded regime history bar
│   │   │   └── GreeksHeatmap.tsx       # Portfolio Greeks exposure
│   │   ├── history/
│   │   │   ├── TradeLogTable.tsx        # Sortable/filterable trade log
│   │   │   ├── StrategyBreakdown.tsx    # Win rate by strategy type
│   │   │   └── PnlWaterfall.tsx         # Per-trade P&L waterfall chart
│   │   └── audit/
│   │       ├── AuditLog.tsx             # Searchable decision log
│   │       └── JSONViewer.tsx           # Collapsible JSON tree viewer
│   │
│   ├── hooks/
│   │   ├── useWebSocket.ts             # Socket.IO connection hook
│   │   └── usePortfolio.ts             # Portfolio state management hook
│   │
│   ├── lib/
│   │   ├── api.ts                      # Fetch wrapper for backend REST API
│   │   ├── types.ts                    # TypeScript interfaces (mirrors Pydantic models)
│   │   └── utils.ts                    # Formatting helpers (currency, percent, date)
│   │
│   └── public/
│       └── volhelix-logo.svg           # Brand logo
│
└── scripts/                            # ── Utility Scripts ──
    ├── setup_paper_account.py          # Initialize fresh $100k paper account
    ├── generate_writeup.py             # CLI to generate ONE_PAGER.md
    ├── test_mcp_connection.py          # Verify Alpaca MCP server connectivity
    └── seed_iv_history.py              # Backfill IV history for IV Rank calculations
```

---

## 13. Alpaca MCP Integration Reference

### 13.1 MCP Server Configuration

```json
{
  "mcpServers": {
    "alpaca": {
      "command": "npx",
      "args": ["-y", "@alpacahq/mcp-server"],
      "env": {
        "ALPACA_API_KEY": "<your-paper-key>",
        "ALPACA_API_SECRET": "<your-paper-secret>",
        "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
        "ALPACA_TOOLSETS": "account,trading,options-data,stock-data,assets,news"
      }
    }
  }
}
```

> **Note:** The `ALPACA_TOOLSETS` env var controls which tool categories are exposed. For our use case we need: `account`, `trading`, `options-data`, `stock-data`, `assets`, and `news`.

### 13.2 Critical MCP Tool Calls (With Examples)

```python
# ── 1. Account Check ──
account = await mcp.call("get_account_info")
# Returns: { equity, buying_power, cash, portfolio_value, ... }

# ── 2. Market Clock ──
clock = await mcp.call("get_clock")
# Returns: { is_open, next_open, next_close }

# ── 3. Stock Snapshot (current price) ──
snapshot = await mcp.call("get_stock_snapshots", {
    "symbols": "NVDA,SPY,QQQ,AAPL,TSLA"
})

# ── 4. Historical Bars (for indicators) ──
bars = await mcp.call("get_stock_bars", {
    "symbols": "NVDA",
    "timeframe": "1Day",
    "start": "2025-09-01",
    "end": "2026-09-01",
    "limit": 252  # ~1 year of trading days
})

# ── 5. VIX Index (for regime detection) ──
vix = await mcp.call("get_latest_index_values", {
    "symbols": "VIX"
})

# ── 6. Options Chain (with Greeks!) ──
chain = await mcp.call("get_option_chain", {
    "underlying_symbol": "NVDA",
    "expiration_date": "2026-09-06",
    "type": "put",
    "strike_price_gte": "110",
    "strike_price_lte": "130"
})
# Returns: contracts with { symbol, strike, expiry, greeks: { delta, gamma, theta, vega, rho }, implied_volatility, ... }

# ── 7. Option Snapshots (specific contracts) ──
opt_snap = await mcp.call("get_option_snapshots", {
    "symbols": "NVDA260906P00120000,NVDA260906P00115000"
})

# ── 8. Place Multi-Leg Order ──
order = await mcp.call("place_order", {
    "order_class": "mleg",
    "type": "limit",
    "time_in_force": "day",
    "limit_price": "1.25",
    "legs": [
        {
            "symbol": "NVDA260906P00120000",
            "side": "sell",
            "ratio_qty": "1"
        },
        {
            "symbol": "NVDA260906P00115000",
            "side": "buy",
            "ratio_qty": "1"
        }
    ]
})

# ── 9. Check Order Status ──
orders = await mcp.call("get_orders", {
    "status": "open",
    "limit": 10
})

# ── 10. Get Positions ──
positions = await mcp.call("get_positions")

# ── 11. Close Position (stop-loss / take-profit) ──
close = await mcp.call("close_position", {
    "symbol_or_id": "<position-id-or-symbol>"
})

# ── 12. Portfolio History (for equity curve) ──
history = await mcp.call("get_portfolio_history", {
    "period": "1W",
    "timeframe": "1H"
})

# ── 13. News (for event risk scanner) ──
news = await mcp.call("get_news", {
    "symbols": "NVDA,AAPL",
    "limit": 10
})
```

### 13.3 OCC Symbol Format

Options use standard OCC symbology:
```
NVDA260906P00120000
│    │     │ │
│    │     │ └── Strike price × 1000 (120.00 → 00120000)
│    │     └──── Contract type (P = Put, C = Call)
│    └────────── Expiry date (YYMMDD → 2026-09-06)
└─────────────── Underlying ticker
```

### 13.4 Environment Variables

```env
# ── Alpaca (REQUIRED — paper trading) ──
ALPACA_API_KEY=your_paper_api_key
ALPACA_API_SECRET=your_paper_api_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# ── LLM (FREE — Google Gemini) ──
GOOGLE_API_KEY=your_google_ai_studio_key
LLM_MODEL=gemini-2.5-flash            # Free tier: 10-15 RPM, 1500 RPD

# ── Fallback LLM (Optional — if Gemini rate-limited) ──
# GROQ_API_KEY=your_groq_key           # Free: 30 RPM, Llama 3.3 70B
# OPENROUTER_API_KEY=your_openrouter_key # Free: 20 RPM, various models

# ── Trading Config ──
TRADING_INTERVAL_MINUTES=5
INITIAL_CAPITAL=100000
WATCHED_UNDERLYINGS=SPY,QQQ,AAPL,NVDA,TSLA

# ── Server ──
API_PORT=8000
DASHBOARD_PORT=3000
LOG_LEVEL=INFO
```

---

## 14. Build Execution Plan

### Phase 1: Foundation (Day 1 — ~4 hours)

| # | Task | Output | Priority |
|---|---|---|---|
| 1.1 | Init repo, `pyproject.toml`, `requirements.txt`, `.env.example`, `.gitignore` | Project scaffold | 🔴 |
| 1.2 | Define all Pydantic models (`models/`) — single source of truth | Type-safe data contracts | 🔴 |
| 1.3 | Build Alpaca MCP client wrapper (`mcp/client.py`, `mcp/tools.py`) | Working MCP connection | 🔴 |
| 1.4 | Implement portfolio store (`store/portfolio_store.py`) | In-memory state | 🔴 |
| 1.5 | Setup FastAPI app with health check + Socket.IO mount | Running backend | 🔴 |
| 1.6 | Init Next.js project: Tailwind + shadcn/ui + dark theme layout | Running frontend shell | 🟡 |

**Milestone:** Backend runs, MCP connects and returns account data, frontend shell loads

---

### Phase 2: Core Engine (Day 2 — ~6 hours)

| # | Task | Output | Priority |
|---|---|---|---|
| 2.1 | `engine/indicators.py` — RSI, SMA, Bollinger Bands, squeeze detection | Technical indicators | 🔴 |
| 2.2 | `engine/iv_calculator.py` — IV Rank, IV Percentile + `scripts/seed_iv_history.py` | IV metrics | 🔴 |
| 2.3 | `engine/regime.py` — Regime classifier (rules-based first, HMM stretch) | Regime detection | 🔴 |
| 2.4 | `engine/strategy_builder.py` — Build all 5 strategy types from Greeks targets | Strategy construction | 🔴 |
| 2.5 | `engine/position_sizer.py` — Kelly Criterion + regime adjustments | Smart position sizing | 🟡 |
| 2.6 | `risk/risk_gate.py` — All 10 hard-coded rules | Deterministic risk gate | 🔴 |
| 2.7 | `risk/circuit_breaker.py` — Daily drawdown halt | Capital protection | 🔴 |
| 2.8 | `risk/exit_manager.py` — Stop-loss & take-profit monitor | Auto exits | 🔴 |
| 2.9 | Write unit tests for Risk Gate, Regime, IV Calculator | Test coverage | 🟡 |

**Milestone:** Full engine works: regime detection → strategy building → risk gate validation

---

### Phase 3: Multi-Agent System (Day 3 — ~6 hours)

| # | Task | Output | Priority |
|---|---|---|---|
| 3.1 | `agents/market_intel.py` — Market scanning + thesis generation | Market signals | 🔴 |
| 3.2 | `agents/strategy_synthesizer.py` — Strategy proposals from signals | Trade proposals | 🔴 |
| 3.3 | `agents/devils_advocate.py` — Counter-argument agent | Debate mechanism | 🔴 |
| 3.4 | `agents/consensus.py` — Weighted voting engine (deterministic) | Consensus check | 🔴 |
| 3.5 | `agents/executor.py` — MCP tool calling for trade execution | Live execution | 🔴 |
| 3.6 | `agents/orchestrator.py` — LangGraph state machine (full pipeline) | Complete agent loop | 🔴 |
| 3.7 | `agents/event_scanner.py` — Earnings + economic calendar + news | Event awareness | 🟡 |
| 3.8 | `agents/post_mortem.py` — Self-reflective analysis on trade close | Learning loop | 🟡 |
| 3.9 | `scheduler.py` — APScheduler 5-min loop during market hours | Autonomous operation | 🔴 |

**Milestone:** Full autonomous cycle: scan → propose → debate → risk check → execute (on paper account)

---

### Phase 4: Dashboard (Day 4 — ~5 hours)

| # | Task | Output | Priority |
|---|---|---|---|
| 4.1 | Layout: Sidebar, Header, dark theme, routing between 4 pages | App shell | 🔴 |
| 4.2 | Command Center: MetricCards (equity, P&L, win rate, Sharpe, regime) | Key metrics | 🔴 |
| 4.3 | Command Center: EquityCurve (Recharts — VolHelix vs SPY) | Performance viz | 🔴 |
| 4.4 | Command Center: PositionsTable (active positions with Greeks) | Position monitoring | 🔴 |
| 4.5 | Command Center: ReasoningFeed (live scrolling agent thoughts) | Transparency | 🔴 |
| 4.6 | WebSocket: `useWebSocket.ts` hook + Socket.IO event handlers | Real-time updates | 🔴 |
| 4.7 | Volatility Lab: 3D vol surface (Plotly.js) + IV gauges | Wow factor 🌋 | 🟡 |
| 4.8 | Trade History: TradeLogTable + StrategyBreakdown charts | Analytics | 🟡 |
| 4.9 | Audit Trail: searchable log + JSON viewer + export to MD | Judge transparency | 🟡 |
| 4.10 | Backend REST routes (`api/routes.py`) for all dashboard data | API endpoints | 🔴 |

**Milestone:** Dashboard shows live data — equity curve, positions, reasoning feed, all 4 pages functional

---

### Phase 5: Integration, Polish & Submission (Day 5 — ~4 hours)

| # | Task | Output | Priority |
|---|---|---|---|
| 5.1 | End-to-end integration test: full agent cycle on paper account | Working system | 🔴 |
| 5.2 | `utils/writeup_generator.py` — Auto-generate ONE_PAGER.md | Submission doc | 🔴 |
| 5.3 | Docker Compose setup (backend + frontend + MCP) | One-command deploy | 🟡 |
| 5.4 | Error handling hardening: API failures, MCP disconnects, edge cases | Robustness | 🔴 |
| 5.5 | Let system run autonomously for 2+ hours; monitor for issues | Stability proof | 🔴 |
| 5.6 | Record demo screenshots / video of dashboard | Submission assets | 🔴 |
| 5.7 | Final compliance matrix check (all 6 requirements met) | Ready to submit | 🔴 |
| 5.8 | Submit: code repo + ONE_PAGER.md + demo assets | 🏆 Submitted | 🔴 |

**Milestone:** Polished, tested, documented, and submitted

---

### Sprint Calendar

```
Day 1 (Sep 1) ✓ Backend scaffold + MCP + models + frontend shell
Day 2 (Sep 2) ✓ Core engine: regime, IV, strategies, risk gate, tests
Day 3 (Sep 3) ✓ All 7 agents + orchestrator + scheduler → autonomous trading live
Day 4 (Sep 4) ✓ Dashboard: 4 pages, real-time WebSocket, 3D vol surface
Day 5 (Sep 4) ✓ Integration, polish, run live, generate write-up, SUBMIT
```

---

## 15. One-Page Write-Up Auto-Generator

The `utils/writeup_generator.py` script pulls live portfolio data and generates the required hackathon submission document:

```python
def generate_writeup(portfolio: PortfolioSnapshot, trades: list[TradeRecord]) -> str:
    wins = [t for t in trades if t.realized_pnl and t.realized_pnl > 0]
    losses = [t for t in trades if t.realized_pnl and t.realized_pnl <= 0]
    win_rate = len(wins) / max(len(wins) + len(losses), 1)

    return f"""# VolHelix AI — Hackathon Submission

## AI Logic
7-agent architecture with structured debate protocol:
1. **Market Intel** — IV Rank, regime classification (HMM-based)
2. **Strategy Synthesizer** — Greeks-optimized options spreads per regime
3. **Devil's Advocate** — challenges thesis, finds tail risks
4. **Event Scanner** — earnings, FOMC, news sentiment monitoring
5. **Consensus Engine** — weighted 2/3 agreement required (deterministic)
6. **Deterministic Risk Gate** — 10 hard-coded rules, ZERO LLM (pure Python)
7. **MCP Executor** — multi-leg orders via Alpaca MCP Server

## Risk Management (Deterministic — No LLM)
- Max 2.5% NAV per position | Max 3% daily drawdown circuit breaker
- Stop-loss at -50% of credit | Take-profit at +60% max profit
- Portfolio delta capped | Single-stock concentration < 30%
- Min 3 DTE | Min 100 OI | Max 8 simultaneous positions
- {sum(1 for t in trades if t.status == "STOPPED_OUT")} stop-outs triggered

## Alpaca Infrastructure
- All trades via **Alpaca MCP Server** (place_order, get_option_chain, get_positions, etc.)
- Paper account: ${portfolio.total_equity:,.0f} ({portfolio.total_pnl_pct:+.2%} return)
- {len(trades)} total trades | {win_rate:.0%} win rate

| Metric | Value |
|---|---|
| Starting Capital | $100,000 |
| Current Equity | ${portfolio.total_equity:,.0f} |
| Total Return | {portfolio.total_pnl_pct:+.2%} |
| Max Drawdown | (auto-calculated) |
| Win Rate | {win_rate:.0%} |
| Trades | {len(trades)} |
"""
```

---

## 16. Testing & Verification

### 16.1 Unit Tests

```bash
# Run full test suite
cd backend && python -m pytest tests/ -v --tb=short

# Key test coverage:
# test_risk_gate.py        → All 10 rules, boundary values, multi-check failures
# test_regime.py            → Each regime boundary, VIX transitions, squeeze detection
# test_iv_calculator.py     → IV Rank = 0 (at low), = 1 (at high), percentile accuracy
# test_strategy_builder.py  → All 5 strategy types, leg construction, P&L calculations
# test_position_sizer.py    → Kelly Criterion edge cases (0% win rate, 100% win rate)
# test_consensus.py         → Weighted voting: pass at 66%, fail below, tie-breaking
```

### 16.2 Integration Tests

```bash
# 1. Verify MCP server connectivity
python scripts/test_mcp_connection.py
# Expected: Account info returned, buying power > $90,000

# 2. Dry run (full agent cycle, no execution)
python -m backend.agents.orchestrator --dry-run
# Expected: Completes market scan → strategy proposal → debate → risk check, stops before execution

# 3. Single live cycle on paper
python -m backend.agents.orchestrator --live --once
# Expected: Places one real trade on paper account (or correctly rejects if risk gate fails)

# 4. Multi-cycle run (30 min)
python -m backend.scheduler --duration 30
# Expected: 6 cycles complete, trades executed, no crashes
```

### 16.3 Verification Checklist

- [ ] MCP server connects and returns account data
- [ ] IV Rank and IV Percentile match manual calculations on known data
- [ ] Regime classifier: VIX=12 → LOW_VOL, VIX=25 → ELEVATED, VIX=35 → CRISIS
- [ ] Risk Gate rejects: position > 2.5% NAV, DD > 3%, delta overload, DTE < 3
- [ ] Risk Gate approves: valid spread within all 10 thresholds
- [ ] Circuit breaker halts all trading when daily DD > 3%
- [ ] Multi-leg order executes on paper and fill is confirmed
- [ ] Stop-loss triggers and closes position automatically
- [ ] Devil's Advocate produces counter-arguments and votes DISAGREE when appropriate
- [ ] Consensus engine correctly blocks trade when < 66% agreement
- [ ] Dashboard MetricCards update in real-time via WebSocket
- [ ] Equity curve renders with SPY benchmark
- [ ] Reasoning feed shows live agent thoughts in correct order
- [ ] 3D vol surface renders and is interactive (rotate/zoom)
- [ ] Audit trail is searchable and JSON viewer works
- [ ] ONE_PAGER.md generates with correct live metrics
- [ ] System runs autonomously for 2+ hours without crash

---

## 17. Risk Disclosure & Edge Cases

### 17.1 Known Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **LLM hallucination** → invalid strategy or bad strikes | Deterministic Risk Gate validates every proposal; no trade executes without passing 10 hard-coded checks |
| **Options illiquidity** → wide bid-ask, no fills | Liquidity check (OI > 100, bid-ask < 20%) in Risk Gate; only trade SPY, QQQ, AAPL, NVDA, TSLA |
| **Regime misclassification** → wrong strategy for conditions | Post-Mortem Agent tracks accuracy; system reduces size in uncertain regimes; Crisis mode → cash |
| **API rate limits** → missed cycles | 5-minute interval (well within limits); exponential backoff on 429s |
| **MCP server disconnection** → can't execute | Health check pings every cycle; circuit breaker on 3 consecutive failures; no blind retries |
| **0 DTE / near-expiry risk** → gamma explosion | MIN_DTE = 3 enforced in Risk Gate; no same-day or next-day expiry trades |
| **Correlated positions** → all-in on one sector | Single-underlying < 30% cap; diversification across 5 underlyings; max 2 same-ticker positions |
| **Partial multi-leg fill** → unhedged risk | Atomic `order_class: mleg` ensures all legs fill together or none fill |
| **Paper vs Live divergence** → fills may not represent real market | Acknowledged limitation; system designed for paper-only competition use |

### 17.2 Edge Cases Handled

| # | Edge Case | Handling |
|---|---|---|
| 1 | **Market closed** | Scheduler checks `get_clock()` — only runs 9:30 AM – 4:00 PM ET, skips weekends/holidays |
| 2 | **Options chain empty** (no contracts match criteria) | Skip underlying for this cycle, log warning, try next |
| 3 | **Order rejected by Alpaca** (insufficient BP, invalid symbol) | Log rejection reason with full detail, do not retry, alert on dashboard |
| 4 | **All agents disagree** (consensus < 66%) | No trade — log the full debate, display in reasoning feed, skip cycle |
| 5 | **IV data unavailable** for a contract | Fall back to nearest-strike IV interpolation, flag in audit |
| 6 | **Buying power insufficient** after recent trade | Buying power check in Risk Gate catches this; rejects cleanly |
| 7 | **Daily drawdown hits 3%** at market open | Circuit breaker engages immediately, no new trades for rest of day, positions held |
| 8 | **LLM timeout / API error** | Retry once with 5s delay, then skip cycle, log error |
| 9 | **Weekend/after-hours trigger** | Check market clock first; if closed, return early with "market closed" status |
| 10 | **Portfolio starts at $0** | Detect < \$1,000 equity → refuse to trade, prompt for account initialization |

---

> **Document Version:** 1.0
> **Last Updated:** September 1, 2026
> **Author:** VolHelix AI Team
> **Status:** 🟢 Ready for Build Execution
> **Hackathon Deadline:** September 4, 2026
