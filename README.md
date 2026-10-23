# VolHelix AI 🧬

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg)](https://fastapi.tiangolo.com)
[![Next.js 16.4.3](https://img.shields.io/badge/Next.js-16.4.3-black.svg)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6.svg)](https://www.typescriptlang.org/)

**Crypto order-flow research and testnet trading, with production Spot and USDT perpetual market data.**

VolHelix combines a charcoal and amber trading workspace, searchable Binance
markets, footprint/DOM/tape/heatmap/profile/CVD panels, a deterministic risk
gate, and a persisted order lifecycle. The five pages are `/`, `/terminal`,
`/volatility`, `/audit`, and `/history`. The volatility surface is an explicitly
illustrative model, not a quoted options chain or a trading signal.

## Market and execution behavior

- Market data comes from Binance production public APIs and streams. Public
  discovery supports active USDT Spot pairs and USDT-margined perpetual Futures.
  A production listing does not guarantee availability on the testnet.
- Spot execution uses `testnet.binance.vision`. Futures execution uses
  `demo-fapi.binance.com`, separate credentials, one-way positions, single-asset
  USDT margin and **1x symbol leverage**. Configure these in Binance demo first;
  the application rejects unsupported settings and never changes account modes.
- Manual market and limit orders use server-validated previews and confirmation.
  The server rechecks exchange filters, funds, exposure, drawdown and the existing
  0.70 entry confluence threshold before dispatch. Spot sells reduce tracked
  holdings; Futures exits are reduce-only. Spot cannot create short positions.
- Auto-Pilot and manual Scan & Trade remain **Spot-only**. Futures uses the manual
  ticket. The guardian monitors persisted filled exposure while the backend is
  running, including when scanning is paused; stopping the backend stops that
  protection. Importing the application alone starts no trading thread.
- An acknowledgement is not a fill. Pending, partial, rejected, canceled and
  uncertain outcomes remain distinct. Stable client IDs and persisted intents
  reconcile uncertain responses instead of blindly resubmitting. “Fill Now”
  reconciles actual exchange state; it does not manufacture a fill.
- Actual commissions are shown separately in their native assets with coverage
  flags. Realized/unrealized price PnL is **gross**, and net realized PnL is
  unavailable. Spot base-asset fees reduce sellable inventory; unsellable lot-step
  or minimum-notional residue remains open as dust.
- Account values require verified reads. Missing data stays unavailable, and
  retained observations are labelled stale. `INITIAL_CAPITAL` does not create
  wallet funds or an account PnL baseline. Spot drawdown coverage starts with the
  first observed daily/session equity; losses before observation are unknown.

The flow engine scopes rooms, caches and state by market plus symbol. It bounds
subscriptions and buffers, broadcasts at fixed rates, and reports LIVE only after
fresh trades and synchronized depth. Missing data is never replaced with invented
market values. See [transport contracts](docs/FLOW_MARKETS.md) and
[execution, fee and runtime contracts](docs/EXECUTION_FEES_AND_RUNTIME.md).

## Local setup

Verified runtime: Python 3.13.7 and Node 24.18.1; Docker uses Python 3.13 and
Node 22. Next.js requires Node 20.9 or newer. Run commands from the repository
root, using two terminals for the servers.

```powershell
python -m venv env
.\env\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item .env.example .env
# Edit .env locally; never commit credentials.
.\env\Scripts\python.exe -m backend.main
```

```powershell
cd frontend
npm ci
npm run dev
```

Open [the dashboard](http://localhost:3000) or
[the order-flow terminal](http://localhost:3000/terminal).
Public streams need no keys. Leave credentials blank for public-data exploration;
account and trading features will be unavailable. Spot testnet credentials come
from [Binance Spot Testnet](https://testnet.binance.vision/). Set
`BINANCE_FUTURES_API_KEY` and `BINANCE_FUTURES_API_SECRET` separately for Futures
demo. `GOOGLE_API_KEY` is used by the Gemini agent workflow. No production trading
credentials are needed. Testnet resets, liquidity and instrument availability can
differ from production; there is no promise of execution at the displayed price.

Startup opens local ledgers under `backend/data` and starts guardian protection
for any existing tracked exposure. Use a fresh checkout/ledger for an empty
workspace. Do not copy a live ledger into a verification environment.

REST uses Next's `BACKEND_URL` rewrite (local default `http://127.0.0.1:8000`).
Socket.IO needs a browser-reachable `NEXT_PUBLIC_SOCKET_URL`, falling back to the
documented local endpoint. Rebuild after changing public build-time values.
`CORS_ORIGINS` is an explicit comma-separated frontend allowlist. Docker setup,
persistent volumes and endpoint configuration are described in
[runtime configuration](docs/EXECUTION_FEES_AND_RUNTIME.md#runtime-and-local-configuration).
`docker compose up --build` starts the application lifecycle; it is not a test.

## Verification

From a fresh checkout with no private `.env`:

```powershell
.\env\Scripts\python.exe -m pytest -q
cd frontend
npm run lint
npx tsc --noEmit
npm run build
npx playwright test
npm audit
```

On 2026-10-24, the current runtime passed **329 isolated backend tests**,
**59 fixture-backed browser tests**, lint, TypeScript and production build;
`npm audit` reported zero vulnerabilities. Backend tests reject unexpected network
calls, use temporary databases, and suppress trading loops. Browser tests use
`.next-e2e` and a local controlled Socket.IO server; screenshots in
[`docs/artifacts/ui/task-8b`](docs/artifacts/ui/task-8b) are labelled offline
fixtures. The browser run covers all five routes at 390/768/1440px, keyboard and
dialog behavior, price precision, reduced motion, market isolation and outcomes.

Separate read-only public checks:

```powershell
.\env\Scripts\python.exe scripts/test_mcp_connection.py --market spot --symbol BTCUSDT
.\env\Scripts\python.exe scripts/test_mcp_connection.py --market futures --symbol BTCUSDT
```

Both hosts timed out in the final verification environment. Current live exchange
connectivity and a screenshot backed by live public data are therefore unverified;
earlier Futures stream evidence is dated separately. No automated verification
submitted an order or started Auto-Pilot. Authenticated execution and production
readiness remain unverified. See [exact results and limitations](docs/UPGRADE_VERIFICATION.md).

## Project references

- [Approved upgrade design](docs/superpowers/specs/2026-10-20-market-upgrade-design.md)
- [Implementation plan](docs/superpowers/plans/2026-10-20-market-upgrade.md)
- [Order-flow guardrails](Upgrade_Plan.md#21-guardrails--never-do-these)
- [Original product requirements](PRD.md) and [innovation notes](INNOVATION.md)

## License

MIT.
