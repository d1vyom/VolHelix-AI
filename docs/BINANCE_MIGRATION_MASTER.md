# VolHelix AI — Alpaca → Binance Migration: Master Guide

> **Objective:** Completely remove Alpaca from the project and replace it with Binance for **Crypto-only** trading.  
> **Trading Mode:** Real market data from Binance + Paper trading on Binance Spot Testnet (no real money).  
> **Scope:** Backend (Python), Frontend (Next.js/TypeScript), Config, Dependencies, Docker — every layer.

---

## Table of Contents

1. [Migration Overview](#1-migration-overview)
2. [Binance API Keys & Testnet Setup](#2-binance-api-keys--testnet-setup)
3. [Environment Variables (.env)](#3-environment-variables-env)
4. [Document Index](#4-document-index)
5. [Migration Execution Order](#5-migration-execution-order)
6. [Critical Rules & Constraints](#6-critical-rules--constraints)
7. [Verification Checklist](#7-verification-checklist)

---

## 1. Migration Overview

### What Changes

| Layer | Remove (Alpaca) | Replace With (Binance) |
|---|---|---|
| **Dependencies** | `alpaca-py`, `alpaca-mcp-server` | `python-binance` (or `binance-connector-python`) |
| **Config** | `ALPACA_API_KEY`, `ALPACA_API_SECRET`, `ALPACA_BASE_URL` | `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `BINANCE_BASE_URL`, `BINANCE_USE_TESTNET` |
| **MCP Client** | `backend/mcp/client.py` (AlpacaClient) | `backend/mcp/client.py` (BinanceClient) |
| **MCP CLI Runner** | `backend/mcp/cli_runner.py` (Alpaca MCP) | Remove entirely (not applicable) |
| **API Routes** | All `/api/alpaca/*` endpoints | All `/api/exchange/*` endpoints (or rename to `/api/binance/*`) |
| **Engine: Auto Trader** | `backend/engine/auto_trader.py` uses Alpaca SDK | Replace with Binance SDK calls |
| **Engine: Order Flow** | `backend/engine/order_flow.py` uses Alpaca data | Replace with Binance market data |
| **Agents** | Agents import `AlpacaClient` | Agents import `BinanceClient` |
| **Frontend API** | `frontend/src/lib/api.ts` calls `/api/alpaca/*` | Frontend calls `/api/exchange/*` |
| **Frontend Components** | References to "Alpaca" in UI text | Replace with "Binance" |
| **Watched Symbols** | `SPY,QQQ,AAPL,NVDA,TSLA` (US Stocks) | `BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT` (Crypto pairs) |
| **Market Hours** | US Market 09:30-16:00 ET | 24/7 Crypto markets |
| **Options** | Options strategies (spreads, condors) | Spot trading only (for now) |

### What Stays the Same

- Multi-agent architecture (Market Intel, Strategy, Devil's Advocate, etc.)
- Risk Gate (10 deterministic rules — adapted for crypto spot trading)
- Volatility Regime Engine (adapted to use crypto volatility metrics)
- Dashboard UI structure (4 pages)
- WebSocket real-time updates
- SQLite trade log persistence
- LLM integration (Google Gemini)

---

## 2. Binance API Keys & Testnet Setup

### How the Dual-Mode Architecture Works

```
┌─────────────────────────────────────────────────────────┐
│                    BINANCE DUAL MODE                     │
│                                                          │
│  ┌─────────────────────┐   ┌──────────────────────────┐ │
│  │  REAL MARKET DATA   │   │  PAPER TRADING (TESTNET) │ │
│  │  (Production API)   │   │  (Testnet API)           │ │
│  │                     │   │                          │ │
│  │  • Live prices      │   │  • Place orders          │ │
│  │  • Real order books │   │  • Check balances        │ │
│  │  • Klines/candles   │   │  • View positions        │ │
│  │  • 24hr tickers     │   │  • Order history         │ │
│  │  • Recent trades    │   │  • Cancel orders         │ │
│  │                     │   │                          │ │
│  │  NO API KEY NEEDED  │   │  TESTNET API KEY NEEDED  │ │
│  │  for public data    │   │                          │ │
│  └─────────────────────┘   └──────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### API Keys Needed in `.env`

```env
# ── Binance Spot Testnet (Paper Trading) ──
# Get these from: https://testnet.binance.vision/
# 1. Go to https://testnet.binance.vision/
# 2. Login with your GitHub account
# 3. Click "Generate HMAC_SHA256 Key"
# 4. Copy the API Key and Secret Key
BINANCE_API_KEY=your_testnet_api_key_here
BINANCE_API_SECRET=your_testnet_api_secret_here
BINANCE_USE_TESTNET=true

# Testnet base URL (DO NOT CHANGE)
BINANCE_BASE_URL=https://testnet.binance.vision
```

### Testnet vs Production Endpoints

| Purpose | Testnet URL | Production URL |
|---|---|---|
| **Spot REST API** | `https://testnet.binance.vision` | `https://api.binance.com` |
| **Spot WebSocket** | `wss://testnet.binance.vision/ws` | `wss://stream.binance.com:9443/ws` |
| **Market Data (public)** | Use **production** for real data | `https://api.binance.com` |

> **IMPORTANT:** Market data (prices, candles, order book, tickers) should ALWAYS come from the **production API** (`api.binance.com`) because the testnet has fake/stale data. Only **trading operations** (place order, cancel order, check balance) go through the testnet.

### How to Get Testnet API Keys

1. Navigate to **https://testnet.binance.vision/**
2. Click **"Log In with GitHub"** (use your GitHub account)
3. Click **"Generate HMAC_SHA256 Key"**
4. Label it (e.g., "VolHelix-AI")
5. Copy the **API Key** → paste into `.env` as `BINANCE_API_KEY`
6. Copy the **Secret Key** → paste into `.env` as `BINANCE_API_SECRET`
7. The testnet account comes preloaded with **fake balances** (BTC, ETH, USDT, etc.)

> **WARNING:** Testnet keys expire periodically. If you get `APIError: -2015 Invalid API-key`, regenerate a new key pair from https://testnet.binance.vision/.

---

## 3. Environment Variables (.env)

### New `.env` File (Complete Replacement)

```env
# ═══════════════════════════════════════════
# VolHelix AI — Environment Configuration
# ═══════════════════════════════════════════

# ── Binance Spot Testnet (Paper Trading) ──
# Get keys from: https://testnet.binance.vision/
BINANCE_API_KEY=your_testnet_api_key_here
BINANCE_API_SECRET=your_testnet_api_secret_here
BINANCE_BASE_URL=https://testnet.binance.vision
BINANCE_USE_TESTNET=true

# ── LLM: Google Gemini (REQUIRED — FREE) ──
GOOGLE_API_KEY=your_google_api_key_here
LLM_MODEL=gemini-3.6-flash

# Twelve Data (Optional — falls back to demo if absent)
TWELVEDATA_API_KEY=your_twelve_data_key_here

# ── Trading Configuration ──
TRADING_INTERVAL_MINUTES=5
INITIAL_CAPITAL=10000
WATCHED_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT
MAX_POSITION_PCT=0.025
MAX_DAILY_DRAWDOWN=0.03

# ── Server Ports ──
API_PORT=8000
DASHBOARD_PORT=3000
LOG_LEVEL=INFO
```

### Variables Removed

| Old Variable | Reason |
|---|---|
| `ALPACA_API_KEY` | Alpaca completely removed |
| `ALPACA_API_SECRET` | Alpaca completely removed |
| `ALPACA_BASE_URL` | Alpaca completely removed |

### Variables Changed

| Old Variable | New Variable | Notes |
|---|---|---|
| `WATCHED_UNDERLYINGS=SPY,QQQ,...` | `WATCHED_SYMBOLS=BTCUSDT,ETHUSDT,...` | Crypto pairs instead of stocks |
| `INITIAL_CAPITAL=100000` | `INITIAL_CAPITAL=10000` | Crypto testnet uses USDT |

---

## 4. Document Index

All migration documents are in the `docs/` folder. **Read them in order.**

| # | Document | Purpose |
|---|---|---|
| 1 | `BINANCE_MIGRATION_MASTER.md` | **This file** — Overview, API keys, env vars, execution order |
| 2 | `BINANCE_BACKEND_MIGRATION.md` | Backend Python changes — config, client, agents, engine, routes |
| 3 | `BINANCE_FRONTEND_MIGRATION.md` | Frontend TypeScript changes — API layer, components, types |
| 4 | `BINANCE_API_REFERENCE.md` | Complete Binance REST API reference with Python code examples |
| 5 | `BINANCE_WEBSOCKET_STREAMS.md` | Real-time WebSocket streams for live prices and order updates |
| 6 | `BINANCE_DATA_MODELS.md` | Updated Pydantic models and TypeScript types for crypto |
| 7 | `BINANCE_RISK_GATE_ADAPTATION.md` | Risk Gate rules adapted for crypto spot trading |
| 8 | `FILES_TO_DELETE.md` | Explicit list of files and code blocks to remove |

---

## 5. Migration Execution Order

Execute these steps **in this exact order** to avoid breaking the codebase:

### Phase 1: Dependencies & Config (Do First)

```
1. Update backend/requirements.txt — remove alpaca-py, alpaca-mcp-server; add python-binance
2. Update backend/config.py — remove Alpaca settings; add Binance settings
3. Update .env — remove Alpaca keys; ensure Binance testnet keys are set
4. Update .env.example — same changes
5. Run: pip install python-binance (or pip install -r requirements.txt)
```

### Phase 2: Core Client Replacement

```
6. Rewrite backend/mcp/client.py — replace AlpacaClient with BinanceClient
7. Delete backend/mcp/cli_runner.py (Alpaca MCP specific — not needed)
8. Update all imports across the codebase that reference AlpacaClient
```

### Phase 3: Data Models

```
9. Update backend/models/market.py — change watched symbols, add crypto-specific fields
10. Update backend/models/trade.py — adjust for spot trading (no options legs)
11. Update frontend/src/lib/types.ts — mirror Python model changes
```

### Phase 4: Engine & Agents

```
12. Rewrite backend/engine/auto_trader.py — use BinanceClient instead of Alpaca SDK
13. Update backend/engine/order_flow.py — use Binance market data
14. Update backend/agents/market_intel.py — use Binance market data for analysis
15. Update backend/agents/executor.py — execute trades via Binance testnet
16. Update backend/agents/orchestrator.py — remove Alpaca references
17. Update backend/agents/event_scanner.py — remove Alpaca news, use crypto-relevant sources
18. Update backend/agents/strategy_synthesizer.py — adapt for crypto spot (not options)
```

### Phase 5: API Routes

```
19. Rewrite all /api/alpaca/* routes in backend/api/routes.py to use BinanceClient
20. Rename routes from /api/alpaca/* to /api/exchange/* (or /api/binance/*)
21. Update backend/utils/market_hours.py — crypto trades 24/7 (always open)
```

### Phase 6: Frontend

```
22. Update frontend/src/lib/api.ts — change all endpoint URLs and type names
23. Update frontend/src/components/ — replace "Alpaca" text with "Binance"
24. Update frontend/src/app/ pages — adjust symbol selectors for crypto pairs
25. Update frontend/src/lib/types.ts — match backend model changes
```

### Phase 7: Cleanup

```
26. Delete all files listed in docs/FILES_TO_DELETE.md
27. Remove all Alpaca MCP server config references
28. Update README.md — reflect Binance usage
29. Update docker-compose.yml — remove Alpaca MCP service if any
30. Run tests and verify
```

---

## 6. Critical Rules & Constraints

### DO:

- ✅ Use **production Binance API** for all market data (prices, candles, orderbook)
- ✅ Use **testnet Binance API** for all trading operations (orders, balances)
- ✅ Keep the multi-agent architecture intact
- ✅ Keep the Risk Gate deterministic (no LLM)
- ✅ Keep WebSocket real-time updates
- ✅ Use `python-binance` library (well-maintained, supports both testnet and production)
- ✅ Handle crypto trading 24/7 (no market hours restriction)
- ✅ Use USDT-denominated pairs (BTCUSDT, ETHUSDT, etc.)

### DO NOT:

- ❌ Do NOT use the Binance MCP server from the IDE — that connects to REAL Binance
- ❌ Do NOT import `alpaca-py` or `alpaca-mcp-server` anywhere
- ❌ Do NOT use options-related logic for crypto (spot trading only for now)
- ❌ Do NOT leave any `ALPACA_` environment variables in config
- ❌ Do NOT use testnet for market data (it has fake/stale prices)
- ❌ Do NOT hardcode API keys in source files
- ❌ Do NOT place real money trades — testnet only

---

## 7. Verification Checklist

After migration, verify ALL of these pass:

### Backend Verification

- [ ] `grep -rn "alpaca" backend/` returns ZERO results
- [ ] `grep -rn "ALPACA" backend/` returns ZERO results
- [ ] `pip install -r backend/requirements.txt` succeeds without `alpaca-py`
- [ ] `python -c "from backend.config import settings; print(settings.BINANCE_API_KEY[:8])"` prints testnet key prefix
- [ ] `python -c "from backend.mcp.client import BinanceClient; c = BinanceClient(); print(c.get_account())"` returns testnet balances
- [ ] `python -c "from backend.mcp.client import BinanceClient; c = BinanceClient(); print(c.get_price('BTCUSDT'))"` returns live BTC price
- [ ] Backend starts with `uvicorn backend.main:app --reload` without import errors
- [ ] `/api/health` returns `{"status": "ok"}`
- [ ] `/api/exchange/account` returns testnet account with balances
- [ ] `/api/exchange/quote?symbol=BTCUSDT` returns real live BTC price
- [ ] `/api/exchange/bars?symbol=BTCUSDT&timeframe=1H` returns real historical candles
- [ ] `/api/exchange/order` (POST) places order on testnet successfully
- [ ] `/api/exchange/positions` returns testnet positions
- [ ] `/api/exchange/orders` returns testnet order history

### Frontend Verification

- [ ] `grep -rn "alpaca" frontend/src/` returns ZERO results (case-insensitive, except comments explaining migration)
- [ ] `npm run dev` starts without errors
- [ ] Dashboard loads with crypto symbols (BTCUSDT, ETHUSDT, etc.)
- [ ] Candlestick chart shows real BTC/ETH price data
- [ ] Trade panel can submit orders (routed to testnet)
- [ ] Positions tab shows testnet positions
- [ ] Orders tab shows testnet order history

### Integration Verification

- [ ] Full trading cycle works: Market Intel → Strategy → Risk Gate → Execute (on testnet)
- [ ] WebSocket pushes real-time price updates
- [ ] Auto-trader daemon can scan and execute on testnet
- [ ] Guardian TP/SL loop monitors testnet positions

---

> **Document Version:** 1.0  
> **Created:** September 17, 2026  
> **Purpose:** Master guide for Gemini 3.8 Flash to execute the Alpaca → Binance migration  
> **Status:** 🟢 Ready for Execution
