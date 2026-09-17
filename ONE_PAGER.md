# VolHelix AI — Technical One-Page Summary

> **Platform:** VolHelix AI Autonomous Crypto Volatility Platform  
> **Exchange:** Binance (Dual-Mode: Production Market Data + Spot Testnet Execution)  
> **Starting Capital:** $10,000.00 USDT (Binance Spot Testnet)  
> **Repository:** https://github.com/d1vyom/VolHelix-AI  

---

## 1. AI Logic & Multi-Agent Architecture

VolHelix AI implements a **Neurosymbolic Multi-Agent Trading Swarm** that separates generative market thesis discovery from deterministic risk execution:

- **Adversarial Multi-Agent Swarm (LangGraph + Gemini 2.5 Flash/Pro)**:
  1. **Market Intel Agent**: Computes 365-day Parkinson Realized Volatility, Bollinger Band compression squeeze status, and 24h taker volume imbalance.
  2. **Strategy Synthesizer**: Generates algorithmic spot setups (Vol Breakout, Momentum Expansion, Mean Reversion, Squeeze Scalp, DCA Buy) tuned to the active volatility regime.
  3. **Devil's Advocate Agent**: Explicitly challenges trade proposals by searching for liquidity traps, negative macro catalysts (network upgrades, token unlocks), and order book exhaustion.
  4. **Event Scanner**: Continuously monitors crypto hardforks, tokenomics events, and network upgrade schedules.
  5. **Deterministic Consensus Engine**: Replaces generative consensus with a weighted quorum mathematical formula, eliminating LLM hallucination in agreement.
- **Institutional Confluence Gate (Pre-LLM Filter)**:
  - Fuses **Smart Money Concepts (SMC)** (Order Blocks, Fair Value Gaps) with **20-Level Order Book Depth & Imbalance**.
  - Enforces a strict $\ge 70\%$ confluence threshold before invoking agents, eliminating 90% of noise trades.

---

## 2. Deterministic Crypto Risk Gate & 24/7 Position Guardian

VolHelix AI enforces **Zero-Hallucination Risk Management** with zero LLM involvement in risk decisions:

- **10 Inviolable Mathematical Invariants**:
  1. **Max Capital Risk**: $\le 2.5\%$ NAV per position ($250.00 max allocation on $10,000 USDT capital).
  2. **Stop-Loss Requirement**: Strictly positive stop-loss required on all trades.
  3. **Take-Profit Requirement**: Strictly positive take-profit required on all trades.
  4. **Daily Drawdown Circuit Breaker**: Halts trading if session drawdown hits $3.0\%$ ($300.00).
  5. **Portfolio Exposure Limit**: Aggregate non-USDT exposure $\le 60.0\%$ NAV.
  6. **Single Asset Concentration**: Single coin exposure strictly $\le 30.0\%$ of NAV.
  7. **Max Open Positions**: Capped at 5 concurrent spot positions.
  8. **Minimum Order Size**: Order notional strictly $\ge \$10.00$ USDT (Binance spot minimum).
  9. **Volatility Sizing Multiplier**: Dynamic scaling by market regime ($1.00\times$ in Normal, $0.75\times$ in Elevated, $0.50\times$ in Squeeze, $0.25\times$ in Crisis).
  10. **Correlation Group Limits**: Sector risk gating across correlated clusters (high-cap, alt-L1, payments).
- **24/7 Decoupled Position Guardian**:
  - Scanning is decoupled from risk monitoring into independent execution threads.
  - Pausing Auto-Pilot stops *new* scans, but the **Position Guardian runs 24/7 every 5 seconds**.
  - Dynamically exits trades at structural Take-Profit (nearest FVG / resistance) or Stop-Loss (Order Block floor), ensuring an asymmetric **Risk-to-Reward ratio $\ge 2.0:1$**.

---

## 3. Binance Infrastructure Implementation

The system interacts natively with Binance through three dedicated layers:

1. **Dual-Mode Binance Client (`python-binance`)**:
   - **Production Public API**: Real-time prices, 24hr tickers, 20-level order book depth, and OHLCV klines from `api.binance.com` with zero API key requirement.
   - **Spot Testnet API**: Account balance, spot order placement (market & resting limit orders), cancellations, and position tracking on `testnet.binance.vision`.
   - **Automatic Clock Drift Sync**: Eliminates code `-1021 INVALID_TIMESTAMP` errors via synchronized server time offset compensation.
2. **REST API & Telemetry Routes**:
   - `/api/exchange/account`, `/api/exchange/positions`, `/api/exchange/orders`, `/api/exchange/quote`, `/api/exchange/bars`, `/api/exchange/order`, `/api/exchange/close-position`.
   - Full backward compatibility aliases for legacy clients.
3. **Zero-Lag Terminal with IST / UTC Dual Clocks**:
   - Next.js 16.3 glassmorphism dashboard featuring real-time Binance order book, dual session clocks (**IST UTC+5:30** and **UTC**), WebGL 3D Volatility Surface, and an Audited ACID SQLite Trade Ledger.

---

## 4. Performance & Account Verification

| Parameter | Required Spec | VolHelix AI Status |
|---|---|---|
| **Account Type** | Binance Spot Testnet Account | ✅ Verified & Connected |
| **Starting NAV** | 10,000.00 USDT | ✅ Calibrated ($10,000.00) |
| **Max Risk / Trade** | $\le 2.5\%$ NAV | ✅ Hardcoded ($250.00) |
| **Circuit Breaker** | $3.0\%$ Daily Drawdown | ✅ Active ($300.00) |
| **Automated Test Suite**| Full Test Coverage | ✅ 59 / 59 Tests Passed (100%) |
| **Production Build** | Zero Errors & Zero Warnings | ✅ Prerendered Static Build Clean |