# VolHelix AI — Professional Order Flow Terminal Upgrade Plan

> **Target repo:** `d1vyom/VolHelix-AI`
> **Baseline commit at time of writing:** `e30b47c` (`fix(frontend): remove conflicting block display class in Sidebar Link`)
> **Objective:** Add a real-time, tick-level **order flow engine** (footprint, delta/CVD, DOM ladder, liquidity heatmap, volume profile, time & sales, absorption/imbalance detection) and a **professional multi-panel trading terminal UI** on top of the existing Binance spot integration.
> **Executor:** Autonomous coding agent (Gemini) inside Antigravity IDE.
> **Companion document:** `ANTIGRAVITY_SETUP.md` — everything the human must do by hand (keys, installs, MCP, restarts, verification).

---

## 0. How To Use This Document (Agent Execution Protocol)

**Read this section first. It is binding.**

1. **Execute phases in order.** Phase `N+1` assumes Phase `N` is complete, tested and committed. Do not jump ahead.
2. **One commit per phase.** Commit message format: `feat(flow): phase <N> — <short title>`. Never mix phases in one commit.
3. **Every phase has an "Acceptance Criteria" block.** Do not proceed until every box is satisfiable. If a criterion cannot be met, stop and write the blocker into `docs/FLOW_UPGRADE_LOG.md` instead of improvising a workaround.
4. **Never break what works.** The existing test suite (`backend/tests`, 59 tests) must stay green after every phase. `npm run lint` and `npm run build` in `frontend/` must stay clean after every frontend phase.
5. **Additive only.** Do not delete or rewrite existing modules unless this document explicitly names the file and the change. The existing dashboard at `/` must keep working the whole time; the new terminal is built at a **new route** and only swapped in at Phase 8.
6. **No code is included in this document by design.** Every section gives you: exact file paths, responsibilities, data contracts (JSON shapes), algorithms in plain math, parameter names and defaults, and acceptance tests. Write the implementation yourself in the project's existing style.
7. **Style must match the existing codebase:**
   - Backend: Python 3.13, FastAPI, Pydantic v2 models (`BaseModel`, `Field(description=...)`), `loguru` via `backend/utils/logger.get_logger(name)`, snake_case, type hints on every public function, docstrings on every public function.
   - Frontend: Next.js 16 App Router, React 19, TypeScript strict, `"use client"` on interactive components, Tailwind v4 utility classes with the literal hex palette already in use, `memo()` on heavy components, `lucide-react` icons, `framer-motion` for transitions.
   - Read `frontend/AGENTS.md` before touching any Next.js API — that version has breaking changes vs. your training data; consult `node_modules/next/dist/docs/`.
8. **Never invent market data.** No synthetic/random/mock fallbacks in production paths. If a stream is down, panels show an explicit `DISCONNECTED` state. (The existing `get_exchange_bars` fallback that fabricates candles is a defect — see §19.)
9. **Ask nothing, log everything.** Append a dated line to `docs/FLOW_UPGRADE_LOG.md` at the end of each phase: what changed, what was verified, what is deferred.

---

## 1. Current-State Audit (verified against the repo, not assumed)

### 1.1 Backend

| Path | What it actually does | Relevance to this upgrade |
|---|---|---|
| `backend/main.py` | FastAPI app + `socketio.ASGIApp` wrapper; lifespan inits SQLite stores and starts the Position Guardian thread | **Change:** must also start/stop the new market-data stream service in the lifespan |
| `backend/config.py` | `pydantic_settings.BaseSettings`, reads root `.env`, exposes `settings` singleton; `WATCHED_SYMBOLS` derived from a comma string | **Change:** add the flow config block (§6) |
| `backend/mcp/client.py` | `BinanceClient` — dual-mode. `market_client` = production `python-binance` (no keys), `trading_client` = testnet. All **synchronous REST**. TTL cache, `-1021` clock-drift retry, audit `call_logs`. Alias `AlpacaClient = BinanceClient` still exists | **Reuse as-is** for REST (depth snapshot, exchangeInfo, klines). **Do not** add websockets here — they need their own async service |
| `backend/api/routes.py` | ~1080 lines, all REST. Dual-registered `/api/exchange/*` + legacy `/api/alpaca/*`. In-process TTL cache `_get_cached/_set_cached`. IST formatting of bars | **Change:** add a new router module for flow endpoints; do not bloat this file further |
| `backend/api/websocket.py` | 25 lines. `socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')`, `connect`/`disconnect`, two broadcast helpers (`portfolio_update`, `reasoning_event`). **No rooms, no throttling, no binary** | **Change:** extend with rooms, subscribe/unsubscribe events, throttled flow broadcasts |
| `backend/engine/order_flow.py` | 546 lines. **Bar-level SMC, not tick-level order flow.** Order Blocks, Fair Value Gaps, a synthesized "liquidity heatmap" from swing highs/lows + book levels, `analyze_order_flow()`, `calculate_master_strategy_tp_sl()`, `evaluate_master_strategy_setup()` (weights OB 0.40 / FVG 0.30 / GEX 0.20 / R:R 0.10, gate at ≥ 0.70) | **Keep and extend.** True footprint/delta/CVD goes in new modules; the confluence gate gains new components in Phase 9 |
| `backend/engine/auto_trader.py` | 608 lines, singleton. Scan loop (default 30s) + Position Guardian thread (5s). `_execute_scan_cycle` pulls `get_klines(sym, "1h", 50)` → `analyze_order_flow` → `evaluate_master_strategy_setup`, `ThreadPoolExecutor` across symbols, writes `scanner_diagnostics` | **Change (Phase 9):** inject live flow metrics into the evaluation call |
| `backend/risk/risk_gate.py` | `CryptoRiskGate.evaluate(...)`, 10 deterministic invariants, zero LLM | **Do not modify logic.** Flow features never relax a risk invariant |
| `backend/models/*.py` | Pydantic models: `market`, `trade`, `portfolio`, `debate`, `risk`; `MCPCallLog` lives in `trade.py` | New flow models go in a new module, not here |
| `backend/store/*.py` | `aiosqlite` stores: `trade_log`, `portfolio_store`, `postmortem_store`, `iv_history`, `regime_history` | Optional new store for closed footprint bars (Phase 10, opt-in) |
| `backend/scheduler.py` | APScheduler wrapper; **instantiated in `main.py` import but never started** | Leave alone |
| `backend/tests/` | 12 files, 59 tests, heavy `unittest.mock.patch` usage, `conftest.py` fixtures | New tests must follow the same mocking style — no live network in tests |
| `docs/BINANCE_WEBSOCKET_STREAMS.md` | Already documents `BinanceSocketManager` usage for miniticker / kline / partial depth / trade | **Read it before Phase 2.** It is the house reference. This plan extends it with `aggTrade`, diff-depth sync and lifecycle management |

**Critical finding:** the repo has **zero live websocket ingestion today**. Every "real-time" number in the UI comes from REST polling with 3–30s TTL caches. Order flow analytics are computed from **1h klines**. This is the single biggest gap the upgrade closes.

### 1.2 Frontend

| Path | What it actually does | Relevance |
|---|---|---|
| `frontend/src/app/page.tsx` | 1960 lines, one file. `BybitTradingTerminal`: top ticker bar, 12-col grid (8 = chart + bottom dock with Positions/Pending/History tabs, 4 = `OrderBookWidget` + order-entry/bot panel). Polls REST on intervals | **Do not refactor in place.** New terminal is a new route; this page stays as the "Classic" view until Phase 8 |
| `frontend/src/components/CandlestickChart.tsx` | 647 lines. Hand-rolled **SVG** candles with custom zoom/pan/crosshair, non-passive wheel listener, live last-candle mutation | **Reference implementation** for interaction patterns. The new footprint chart uses **Canvas 2D**, not SVG (see §14.1 rationale) |
| `frontend/src/components/VolSurface.tsx` | Plotly 3D surface, dynamic `import("plotly.js-dist-min")` | Pattern to copy for any heavy lazy-loaded viz |
| `frontend/src/lib/api.ts` | 545 lines. `API_BASE` from `NEXT_PUBLIC_API_URL`, `safeJson` helper with fallbacks, every exchange call + `getAlpaca*` aliases | **Extend via a new sibling module**, do not grow this file |
| `frontend/src/lib/types.ts` | Shared domain types | New flow types go in a new module |
| `frontend/src/components/AppLayout.tsx` / `Sidebar.tsx` / `Header.tsx` | Fixed sidebar (240/68px), custom event `volhelix:sidebar-toggle`, `main` is `max-w-7xl p-4 md:p-6` | **Constraint:** a pro terminal must be full-bleed. Phase 8 adds a layout escape hatch |
| `frontend/src/app/globals.css` | Tailwind v4 `@import`, `@theme`, Bybit palette, `.bybit-panel*` classes, 4px scrollbars | **Design tokens live here.** Extend, never replace (§Appendix B) |
| `frontend/package.json` | next 16.3.4, react 19.2.8, tailwind v4, recharts 3, plotly, framer-motion 13, socket.io-client 4.8.3, lucide-react, radix primitives | socket.io-client already present — reuse it |

**Critical finding:** `socket.io-client` is installed but the terminal page does not consume a live socket for market data; it polls. Phase 6 fixes this.

### 1.3 Behavioural gaps this upgrade must close

| Gap | Today | After upgrade |
|---|---|---|
| Trade granularity | 1h / 1m klines | Individual aggregated trades (`aggTrade`) with aggressor side |
| Delta | Not computed | Per-price-level, per-bar, cumulative (CVD), session-anchored |
| Depth | 20-level REST snapshot, polled | Maintained local L2 book from diff stream + partial-book ladder at 100 ms |
| Heatmap | Synthesized from swing highs/lows (not real liquidity) | Real resting-liquidity heatmap from time-binned book snapshots |
| Volume profile | Not present | Session + visible-range profile with POC / VAH / VAL |
| Tape | Not present | Time & Sales with large-print highlighting |
| Latency | 3–30 s TTL caches | Sub-second push over Socket.IO |
| UI density | Single dashboard page, `max-w-7xl` | Multi-panel, resizable, savable workspace |

---

## 2. Scope

### 2.1 In scope
- Binance **spot** market data websockets (production endpoints, no API key required for public streams).
- Tick-level order flow engine: footprint clusters, delta, CVD, imbalance, stacked imbalance, absorption, POC/VAH/VAL, naked POC, liquidity heatmap, DOM ladder, time & sales, whale prints, VWAP + bands.
- New professional terminal UI with dockable panels and saved layouts.
- Wiring flow metrics into the existing confluence gate and scanner diagnostics (**gated behind a feature flag, default ON only after Phase 9 tests pass**).
- Click-to-trade from the DOM ladder routed through the **existing** `/api/exchange/order` path (testnet execution, unchanged risk gate).

### 2.2 Explicitly out of scope
- Futures/perp streams, funding, open interest, liquidations (spot only for now — see §Appendix D for the extension seam).
- Options/GEX (the `gamma_profile` parameter stays `None` as today).
- Multi-exchange live connectors. The **interface** is designed for it (Phase 2.6) but only Binance is implemented.
- Any Rust component. Any desktop build. Any change of framework.
- Real-money trading. Execution stays on `testnet.binance.vision`.

---

## 3. Reference Projects — What To Take, What Never To Take

You were given four reference projects. Here is exactly how each may be used.

| Project | Stack / License | Use it for | **Hard rule** |
|---|---|---|---|
| **Flowsurface** (`github.com/flowsurface-rs/flowsurface`) | Rust + `iced`, native desktop, **GPL-3.0** | **Visual and UX reference only**: panel taxonomy (Heatmap / Candlestick / Footprint / Time&Sales / DOM), tick-size grouping multipliers, imbalance + naked-POC studies, tick-based (non-time) intervals, layout manager concept | ❌ **Do not copy, port, translate or vendor any Flowsurface source.** VolHelix-AI is MIT (`README.md` → License). GPL-3 code cannot be relicensed into it. Look at screenshots and the README feature list; write original code. Do not add Rust to this repo |
| **CryptoFlow** (browser, TypeScript) | Browser app | Reference for browser-side footprint/heatmap rendering feasibility and canvas layering | ❌ Do not copy source. Verify its license before reading its code at all; if the license is not permissive, treat it as visual reference only |
| **tyumex-trading-terminal** | Windows desktop binary | Reference for **layout ergonomics only**: multi-chart workspace, cluster volume presentation, risk-based order entry, bar replay | ❌ Not embeddable, not cross-platform, irrelevant to a Next.js app. Do not attempt integration |
| **OrderflowChart** (`murtazayusuf/OrderflowChart`, Python + Plotly) | Python lib | Reference for the **data shape** of a footprint dataset: `(bid_size, price, ask_size, identifier)` joined to OHLC by `identifier`. Our `FootprintCell` contract in §8 is deliberately compatible with this shape | ⚠️ Optional dev-only dependency for offline chart validation. **Do not** make it a runtime dependency of the backend and do not render production UI with Plotly footprints (too slow for live ticks) |

**Conclusion for the agent:** the order flow engine and the terminal UI are written **from scratch, in-repo**, in Python + TypeScript. The references define *what good looks like*, not *what to copy*. Add an `docs/FLOW_CREDITS.md` noting Flowsurface as design inspiration with no code reuse.

---

## 4. Target Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│ BINANCE PRODUCTION (public, no API key)                                  │
│   wss://stream.binance.com:9443/stream?streams=...                       │
│     <sym>@aggTrade        aggressor-tagged trades                        │
│     <sym>@depth@100ms     L2 diff updates  → maintained local book       │
│     <sym>@depth20@100ms   partial book     → DOM ladder (no sync needed)  │
│     <sym>@kline_1m        bar open/close boundaries                      │
│   https://api.binance.com/api/v3/depth?limit=1000   (snapshot for sync)   │
└───────────────┬──────────────────────────────────────────────────────────┘
                │ asyncio task per connection, auto-reconnect
┌───────────────▼──────────────────────────────────────────────────────────┐
│ backend/marketdata/  — INGESTION (new)                                   │
│   stream_manager  connection lifecycle, multiplexing, backoff, 24h roll  │
│   normalizer      raw Binance JSON → internal Trade / BookDelta models   │
│   orderbook       local L2 book, snapshot+diff sync, ladder projection   │
│   buffers         per-symbol ring buffers (trades, book snapshots)       │
│   hub             MarketDataHub singleton: state registry + pub/sub      │
└───────────────┬──────────────────────────────────────────────────────────┘
                │ in-process events (asyncio queues)
┌───────────────▼──────────────────────────────────────────────────────────┐
│ backend/engine/  — AGGREGATION (new modules alongside existing)          │
│   footprint          price-bucketed buy/sell volume per bar              │
│   delta_engine       bar delta, CVD, divergence, absorption              │
│   volume_profile     POC / VAH / VAL, session + visible range, naked POC │
│   dom_analytics      ladder, imbalance, walls, iceberg hints             │
│   tape_analytics     time & sales enrichment, whale prints, aggression   │
│   heatmap            time×price liquidity matrix from book snapshots     │
│   flow_confluence    composite live-flow score → existing gate (Phase 9) │
│   order_flow (EXISTING — untouched except Phase 9 hook)                  │
└───────────────┬──────────────────────────────┬───────────────────────────┘
                │ REST snapshots               │ throttled pushes
┌───────────────▼──────────────┐ ┌─────────────▼───────────────────────────┐
│ backend/api/flow_routes.py   │ │ backend/api/websocket.py (extended)     │
│   /api/flow/*  (new router)  │ │   rooms: flow:<SYMBOL>                  │
│   cold start + reload        │ │   events: flow:tape/dom/footprint/...   │
└───────────────┬──────────────┘ └─────────────┬───────────────────────────┘
                │                              │
┌───────────────▼──────────────────────────────▼───────────────────────────┐
│ frontend/src/lib/flow/  — DATA LAYER (new)                               │
│   flowTypes.ts  flowApi.ts  useFlowSocket.ts  useFlowStore.ts            │
│   snapshot-then-stream: REST hydrate → socket patches                    │
└───────────────┬──────────────────────────────────────────────────────────┘
┌───────────────▼──────────────────────────────────────────────────────────┐
│ frontend/src/components/flow/  — PANELS (new)                            │
│   FootprintChart  DOMLadder  TimeAndSales  LiquidityHeatmap              │
│   VolumeProfile   CVDPanel   FlowMetricsStrip  WorkspaceGrid             │
│   route: /terminal  (full-bleed, dockable, layouts in localStorage)      │
└──────────────────────────────────────────────────────────────────────────┘
```

**Core design decisions (do not deviate):**

| Decision | Rationale |
|---|---|
| All aggregation happens **server-side** in Python | One source of truth shared by the UI *and* the trading agents. The bot must see exactly what the trader sees |
| Frontend receives **pre-aggregated** frames, never raw ticks (except the tape, batched) | A 1 ms BTC tape would melt React. Bandwidth and CPU stay bounded |
| Ingestion runs in **asyncio tasks on the FastAPI event loop**, not threads | `python-binance`'s `BinanceSocketManager` is async; the existing Guardian thread pattern is for blocking REST and must not be copied here |
| Existing sync `BinanceClient` is reused for REST snapshots via `run_in_executor` | Never call a blocking REST method directly on the event loop |
| The new terminal is a **new route** (`/terminal`) | Zero risk to the working demo until the swap is deliberate |
| Canvas 2D for footprint + heatmap, SVG/DOM for ladder + tape | 10k+ cells per frame is beyond SVG; ladder/tape need text selection and click targets |
| Feature flags on every new subsystem | A hackathon demo must degrade, never crash |

---

## 5. File Layout After the Upgrade

New files only; existing files marked `[MODIFY]`.

```
backend/
  config.py                                [MODIFY] + flow settings block
  main.py                                  [MODIFY] lifespan starts/stops MarketDataHub
  marketdata/                              NEW PACKAGE
    __init__.py
    models.py                  Trade, BookDelta, BookSnapshot, LadderLevel, StreamHealth
    normalizer.py              raw Binance payload → models; side derivation
    stream_manager.py          connection lifecycle, multiplex, backoff, 24h rotation
    orderbook.py               local L2 book: snapshot+diff sync, grouping, ladder
    buffers.py                 ring buffers (deque maxlen) per symbol
    hub.py                     MarketDataHub singleton + subscriber fan-out
    connectors/
      __init__.py
      base.py                  ExchangeConnector protocol (future multi-exchange)
      binance_spot.py          the only implementation for now
  engine/
    order_flow.py                          [MODIFY] Phase 9 hook only
    auto_trader.py                         [MODIFY] Phase 9 hook only
    flow_models.py             NEW  FootprintCell/Bar, VolumeProfile, CVDPoint, ...
    footprint.py               NEW
    delta_engine.py            NEW
    volume_profile.py          NEW
    dom_analytics.py           NEW
    tape_analytics.py          NEW
    heatmap.py                 NEW
    flow_confluence.py         NEW
  api/
    routes.py                              [MODIFY] register flow router only
    websocket.py                           [MODIFY] rooms + throttled flow events
    flow_routes.py             NEW  all /api/flow/* endpoints
    flow_schemas.py            NEW  request/response schemas for the above
  store/
    flow_store.py              NEW (optional, Phase 10) closed-bar persistence
  tests/
    test_normalizer.py         NEW
    test_orderbook_sync.py     NEW
    test_footprint.py          NEW
    test_delta_engine.py       NEW
    test_volume_profile.py     NEW
    test_dom_analytics.py      NEW
    test_heatmap.py            NEW
    test_flow_confluence.py    NEW
    test_flow_routes.py        NEW
    fixtures/
      aggtrades_btcusdt.json   NEW  deterministic replay fixture
      depth_sequence.json      NEW  snapshot + diffs incl. one gap

frontend/src/
  app/
    terminal/page.tsx          NEW  the pro terminal route
    layout.tsx                             [MODIFY] allow full-bleed pages
    globals.css                            [MODIFY] flow design tokens
  components/
    AppLayout.tsx                          [MODIFY] `fullBleed` support
    Sidebar.tsx                            [MODIFY] add "Pro Terminal" nav item
    flow/
      WorkspaceGrid.tsx        NEW  dockable/resizable panel host
      PanelFrame.tsx           NEW  shared chrome: title, settings, collapse
      FootprintChart.tsx       NEW
      DOMLadder.tsx            NEW
      TimeAndSales.tsx         NEW
      LiquidityHeatmap.tsx     NEW
      VolumeProfile.tsx        NEW
      CVDPanel.tsx             NEW
      FlowMetricsStrip.tsx     NEW
      StreamHealthBadge.tsx    NEW
      settings/
        FlowSettingsPopover.tsx NEW  tick grouping, imbalance ratio, thresholds
  lib/
    flow/
      flowTypes.ts             NEW  mirrors backend contracts 1:1
      flowApi.ts               NEW  REST snapshot fetchers
      useFlowSocket.ts         NEW  socket lifecycle + room subscribe
      useFlowStore.ts          NEW  in-memory state, patch application
      flowCanvas.ts            NEW  shared canvas viewport math + renderers
      flowFormat.ts            NEW  price/size/notional formatting, tick rounding

docs/
  FLOW_ARCHITECTURE.md         NEW  written at Phase 11
  FLOW_CREDITS.md              NEW  inspiration credits, no code reuse
  FLOW_UPGRADE_LOG.md          NEW  agent's running log (Phase 0 onward)
```

---

## 6. Configuration Additions

Add to `backend/config.py` inside `Settings` (keep the existing style — plain typed attributes with defaults, `extra="ignore"` already tolerates unknown env keys).

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `FLOW_ENABLED` | bool | `True` | Master switch. `False` → hub never starts, `/api/flow/*` return `503` with `{"enabled": false}` |
| `FLOW_SYMBOLS_STR` (alias `FLOW_SYMBOLS`) | str | `""` | Comma list of streamed symbols. Empty → fall back to `WATCHED_SYMBOLS` |
| `FLOW_WS_BASE_URL` | str | `wss://stream.binance.com:9443` | Never point this at testnet |
| `FLOW_DEPTH_LEVELS` | int | `20` | Partial-book levels for the ladder (allowed: 5, 10, 20) |
| `FLOW_DEPTH_SNAPSHOT_LIMIT` | int | `1000` | REST depth snapshot depth for the maintained book |
| `FLOW_USE_DIFF_DEPTH` | bool | `True` | `False` → ladder + heatmap run off partial book only (lower fidelity, zero sync risk) |
| `FLOW_TICK_GROUP_MULTIPLIER` | float | `1.0` | Price bucket = `tickSize × multiplier`; UI can override per panel |
| `FLOW_FOOTPRINT_INTERVALS_STR` | str | `1m,5m,15m` | Bar intervals maintained server-side |
| `FLOW_FOOTPRINT_BARS` | int | `240` | Bars kept in memory per symbol per interval |
| `FLOW_TAPE_BUFFER` | int | `2000` | Trades retained per symbol |
| `FLOW_TRADE_BUFFER` | int | `50000` | Raw trades retained per symbol for profile/replay |
| `FLOW_HEATMAP_WINDOW_SEC` | int | `600` | Heatmap time window |
| `FLOW_HEATMAP_BIN_MS` | int | `1000` | Heatmap time bin width |
| `FLOW_IMBALANCE_RATIO` | float | `3.0` | Diagonal imbalance threshold (300 %) |
| `FLOW_IMBALANCE_MIN_VOLUME` | float | `0.0` | Ignore imbalances below this base volume (noise filter) |
| `FLOW_STACKED_IMBALANCE_MIN` | int | `3` | Consecutive imbalanced levels to flag a zone |
| `FLOW_VALUE_AREA_PCT` | float | `0.70` | Value area coverage |
| `FLOW_WHALE_NOTIONAL_USD` | float | `100000.0` | Tape highlight threshold |
| `FLOW_LARGE_PRINT_PERCENTILE` | float | `0.99` | Adaptive alternative to the fixed threshold |
| `FLOW_WALL_MULTIPLIER` | float | `5.0` | A level is a "wall" if size ≥ multiplier × median level size |
| `FLOW_BROADCAST_HZ` | float | `4.0` | Metrics/DOM/footprint push rate per symbol |
| `FLOW_TAPE_BROADCAST_HZ` | float | `10.0` | Tape batch push rate |
| `FLOW_MAX_RECONNECT_BACKOFF_SEC` | int | `60` | Exponential backoff ceiling |
| `FLOW_CONFLUENCE_ENABLED` | bool | `False` | Phase 9 gate. Flip to `True` only after Phase 9 tests pass |
| `FLOW_CONFLUENCE_WEIGHT` | float | `0.25` | Share of the composite score owned by live flow |
| `FLOW_PERSIST_BARS` | bool | `False` | Phase 10 opt-in SQLite persistence |

Add a derived `FLOW_SYMBOLS` property (same pattern as `WATCHED_SYMBOLS`) and a `FLOW_FOOTPRINT_INTERVALS` property.

Mirror every one of these into `.env.example` under a new `── Order Flow Engine ──` header, with the same comment style already used in that file. **No new secret is required** — public Binance market streams are unauthenticated.

---

## PHASE 0 — Pre-Flight

**Goal:** establish the safety net before touching anything.

### 0.1 Tasks
1. Create branch `feat/order-flow-terminal` from the current HEAD.
2. Create `docs/FLOW_UPGRADE_LOG.md` with a header and a `## Phase 0` entry.
3. Run the full baseline and record the exact output in the log:
   - `python -m pytest backend/tests -q` → expect 59 passed.
   - `cd frontend && npm run lint` → expect 0 errors.
   - `cd frontend && npm run build` → expect success.
4. Confirm reachability of `https://api.binance.com/api/v3/exchangeInfo?symbol=BTCUSDT` and `wss://stream.binance.com:9443` from the dev machine. If blocked, **stop** and escalate to `ANTIGRAVITY_SETUP.md` §Network.
5. Record, for each of the 5 watched symbols, the `tickSize` (PRICE_FILTER), `stepSize` (LOT_SIZE) and `minNotional` from `exchangeInfo`. Write them into the log. These drive all price bucketing.

### 0.2 Acceptance Criteria
- [ ] Branch exists; baseline test/lint/build results logged.
- [ ] `tickSize` for all 5 symbols recorded.
- [ ] No source file modified yet.

---

## PHASE 1 — Data Contracts

**Goal:** every model that crosses a boundary exists and is tested before any I/O is written. Contracts are defined once in Python and mirrored **exactly** in TypeScript.

### 1.1 `backend/marketdata/models.py`

All Pydantic v2 `BaseModel`, all fields documented with `Field(description=...)` matching the existing house style in `backend/engine/order_flow.py`.

**`Trade`** — one normalized aggregated trade
| Field | Type | Notes |
|---|---|---|
| `symbol` | str | upper case, e.g. `BTCUSDT` |
| `agg_id` | int | Binance `a` — aggregate trade id, used for gap detection |
| `price` | float | `p` |
| `qty` | float | `q`, base asset |
| `quote_qty` | float | derived `price × qty`, the USD notional |
| `ts` | int | `T`, trade time in ms epoch |
| `is_buyer_maker` | bool | raw `m` |
| `side` | str | **derived**: `"SELL"` if `is_buyer_maker` else `"BUY"` — this is the *aggressor* side and is the foundation of every delta number in this system |
| `first_id` / `last_id` | int | `f` / `l`, count of underlying trades = `l - f + 1` |

> **Aggressor rule — memorize it.** Binance `m = true` means the *buyer* was the passive maker, so the *seller* crossed the spread: that volume is **SELL/ask-side/negative delta**. `m = false` → **BUY/bid-side/positive delta**. Getting this backwards silently inverts every panel. There is a mandatory unit test for it.

**`BookDelta`** — one diff-depth event: `symbol`, `first_update_id` (`U`), `final_update_id` (`u`), `bids: list[[price, qty]]`, `asks: list[[price, qty]]`, `event_ts` (`E`). A qty of `0` means *remove that level*.

**`BookSnapshot`** — `symbol`, `last_update_id`, `bids`, `asks`, `ts`, `source` (`"REST"` | `"PARTIAL_STREAM"` | `"MAINTAINED"`).

**`LadderLevel`** — `price`, `bid_size`, `ask_size`, `bid_notional`, `ask_notional`, `is_wall` (bool), `is_poc` (bool), `traded_buy` / `traded_sell` (float, recent traded volume at this price for the ladder's built-in volume column), `depth_pct` (0–1, size relative to the largest level on screen — drives bar width).

**`StreamHealth`** — `symbol`, `connected` (bool), `streams` (list[str]), `last_trade_ts`, `last_book_ts`, `messages_per_sec`, `reconnects`, `book_resyncs`, `gap_events`, `lag_ms` (now − last event time), `status` (`LIVE` | `DEGRADED` | `DISCONNECTED` | `DISABLED`).

### 1.2 `backend/engine/flow_models.py`

**`FootprintCell`** — one price bucket inside one bar
| Field | Type | Notes |
|---|---|---|
| `price` | float | bucket **lower bound**, already rounded to the grouped tick |
| `buy_volume` | float | aggressor-buy base volume |
| `sell_volume` | float | aggressor-sell base volume |
| `total_volume` | float | sum |
| `delta` | float | `buy_volume − sell_volume` |
| `trades` | int | number of aggregated trades |
| `buy_imbalance` | bool | diagonal imbalance vs. the sell side one tick below |
| `sell_imbalance` | bool | diagonal imbalance vs. the buy side one tick above |

> Field names `buy_volume` / `sell_volume` map to OrderflowChart's `bid_size` / `ask_size` convention — document the mapping in a comment so the Python/Plotly reference tool can consume our data unchanged.

**`FootprintBar`**
`symbol`, `interval`, `open_time` (ms), `close_time` (ms), `open`, `high`, `low`, `close`, `volume`, `is_closed` (bool), `cells: list[FootprintCell]` (ascending price), `delta`, `cumulative_delta` (CVD at bar close), `max_delta`, `min_delta`, `delta_percent` (`delta / volume`), `poc_price`, `vah`, `val`, `value_area_volume`, `stacked_buy_imbalance_zones: list[[low, high]]`, `stacked_sell_imbalance_zones: list[[low, high]]`, `is_naked_poc` (bool), `absorption: str|None` (`"BUY_ABSORBED"` | `"SELL_ABSORBED"` | `None`), `tick_group` (float, bucket size used).

**`VolumeProfileLevel`** — `price`, `buy_volume`, `sell_volume`, `total_volume`, `delta`, `is_poc`, `in_value_area`.

**`VolumeProfileSnapshot`** — `symbol`, `mode` (`SESSION` | `VISIBLE` | `FIXED_RANGE`), `start_ts`, `end_ts`, `tick_group`, `levels`, `poc_price`, `vah`, `val`, `total_volume`, `naked_pocs: list[float]`.

**`CVDPoint`** — `ts`, `cvd`, `delta`, `price`, `divergence` (`"BEARISH"` | `"BULLISH"` | `None`).

**`TapeEntry`** — `ts`, `price`, `qty`, `quote_qty`, `side`, `is_whale`, `size_bucket` (`S`|`M`|`L`|`XL`), `price_tick` (`"UP"`|`"DOWN"`|`"SAME"` vs previous print), `aggressive_streak` (int, consecutive same-side prints).

**`HeatmapFrame`** — `ts_bin`, `levels: list[[price, bid_size, ask_size]]`.
**`HeatmapSnapshot`** — `symbol`, `tick_group`, `bin_ms`, `window_sec`, `price_min`, `price_max`, `max_size` (normalizer for colour scale), `frames`, `walls: list[{price, size, side, age_sec, persistence}]`.

**`DomAnalytics`** — `symbol`, `best_bid`, `best_ask`, `spread`, `spread_bps`, `mid`, `bid_depth_n`, `ask_depth_n` (cumulative size over N levels), `book_imbalance` (`(bid − ask) / (bid + ask)`, −1…1), `walls`, `levels: list[LadderLevel]`.

**`FlowMetrics`** — the one object the trading agents consume:
`symbol`, `ts`, `price`, `session_cvd`, `bar_delta`, `delta_percent`, `cvd_slope` (per minute, least-squares over last N points), `cvd_divergence`, `buy_sell_ratio` (rolling 1 min aggressor ratio), `aggression_index` (0–1: share of volume from prints ≥ whale threshold), `absorption_flag`, `stacked_imbalance_bias` (`BUY`|`SELL`|`NEUTRAL`), `poc_price`, `vah`, `val`, `price_vs_value` (`ABOVE_VALUE`|`IN_VALUE`|`BELOW_VALUE`), `book_imbalance`, `spread_bps`, `nearest_bid_wall`, `nearest_ask_wall`, `vwap`, `vwap_upper_1`, `vwap_lower_1`, `trade_rate` (trades/sec), `volume_rate` (base vol/sec), `health: StreamHealth`.

### 1.3 `frontend/src/lib/flow/flowTypes.ts`
Mirror every model above as a TS `interface` with **identical field names in snake_case** (do not camelCase — the wire format is the contract; renaming creates an invisible divergence class of bug). Add union string literal types for every enum-ish field.

### 1.4 Acceptance Criteria
- [ ] `backend/marketdata/models.py` and `backend/engine/flow_models.py` import cleanly; `python -c "import backend.engine.flow_models"` succeeds.
- [ ] `backend/tests/test_normalizer.py` contains the aggressor-side test: `{"m": true}` → `side == "SELL"`, `{"m": false}` → `side == "BUY"`.
- [ ] TS interfaces compile under `npm run build` (import them in a throwaway type-only file if needed, then remove).
- [ ] Existing 59 tests still pass.
- [ ] Commit: `feat(flow): phase 1 — data contracts`.

---

## PHASE 2 — WebSocket Ingestion Layer

**Goal:** a resilient, self-healing market-data service that turns Binance streams into normalized in-memory state. No aggregation yet.

### 2.1 Streams to subscribe (per symbol)

| Stream name | Rate | Feeds |
|---|---|---|
| `<sym_lower>@aggTrade` | per trade | footprint, delta/CVD, tape, volume profile, VWAP |
| `<sym_lower>@depth@100ms` | 100 ms | maintained L2 book → heatmap, walls, deep imbalance |
| `<sym_lower>@depth20@100ms` | 100 ms | DOM ladder (self-contained partial book, no sync required) |
| `<sym_lower>@kline_1m` | 250 ms / on close | authoritative bar boundaries + OHLC reconciliation |

Use a **combined stream** URL: `{FLOW_WS_BASE_URL}/stream?streams=a/b/c/...`. Combined payloads arrive as `{"stream": "<name>", "data": {...}}` — the router dispatches on `stream`.

> Prefer `aggTrade` over `trade`: it collapses same-price, same-side, same-taker-order fills into one message, which is exactly the unit a footprint chart wants, and it is far cheaper on message volume for BTC.

### 2.2 `stream_manager.py` responsibilities
1. Build the stream list from `FLOW_SYMBOLS` × the four stream types.
2. **Chunk into connections**: max 200 streams per connection (hard Binance limit is 1024; stay well under) and one connection per ~5 symbols so a single reconnect does not blind the whole terminal.
3. Maintain one `asyncio.Task` per connection. On exception: log, increment `reconnects`, sleep with **exponential backoff** (1, 2, 4, 8 … capped at `FLOW_MAX_RECONNECT_BACKOFF_SEC`, ±20 % jitter), then rebuild the connection **and force a book resync** for its symbols.
4. **Proactive 24-hour rotation.** Binance closes a connection at the 24 h mark. Rotate at 23 h: open the replacement, let both run for ~2 s, then close the old one. Zero-gap handover.
5. Respect the **5 inbound messages/second** limit for `SUBSCRIBE`/`UNSUBSCRIBE` control frames — queue and pace dynamic subscription changes.
6. Heartbeat watchdog: if no message on a connection for 30 s (any stream), treat as dead and reconnect. Binance sends ping frames roughly every 3 minutes; `python-binance`/`websockets` answers pongs automatically — do not hand-roll this, but **do** verify it in the library version actually installed.
7. Clean shutdown: cancel tasks, await them, close the client session. Must be idempotent and must not hang the FastAPI shutdown.

**Implementation choice:** use `python-binance`'s `AsyncClient` + `BinanceSocketManager.multiplex_socket(streams)` (already documented in `docs/BINANCE_WEBSOCKET_STREAMS.md`). If that manager cannot express the 24 h rotation cleanly, fall back to the `websockets` library directly against the combined-stream URL and add `websockets` to `backend/requirements.txt`. Log which path was chosen.

### 2.3 `orderbook.py` — local L2 book maintenance

This is the single most failure-prone part of the whole upgrade. Follow the procedure exactly:

1. Open the `@depth@100ms` stream and **buffer** events in memory. Do not process yet.
2. Fetch a REST snapshot: `GET /api/v3/depth?symbol=<SYM>&limit=1000` (via the existing sync `BinanceClient` in an executor, or a direct async httpx call).
3. Drop every buffered event whose `u` (final update id) is `<= lastUpdateId` of the snapshot.
4. The **first event applied** must satisfy `U <= lastUpdateId + 1 <= u`. If no buffered event satisfies this, discard the snapshot and restart from step 2.
5. Thereafter each event must satisfy `U == previous_u + 1`. **Any break in that chain is a gap: mark the book `DESYNCED`, increment `gap_events`, and restart the whole procedure from step 1.** Never paper over a gap.
6. Applying an event: for each `[price, qty]` in bids/asks — `qty == 0` → delete the level; else set (not add) the level's size to `qty`.
7. Expose: full sorted book, top-N ladder, cumulative depth, grouped-by-tick projection.
8. Resync backoff: never re-snapshot more than once every 5 s per symbol (protects the REST weight budget — `limit=1000` is a heavy call).

**Degradation path:** if `FLOW_USE_DIFF_DEPTH` is `False`, or a symbol desyncs more than 3 times in 5 minutes, drop that symbol to **partial-book mode** (`@depth20@100ms` only): ladder and top-of-book stay live, deep heatmap/walls switch to a `LIMITED` state in the UI. Log the downgrade. Never crash.

### 2.4 `buffers.py`
Per symbol: `deque(maxlen=FLOW_TRADE_BUFFER)` of `Trade`; `deque(maxlen=FLOW_HEATMAP_WINDOW_SEC*1000//FLOW_HEATMAP_BIN_MS)` of heatmap frames; last `FLOW_TAPE_BUFFER` tape entries. Memory is bounded by construction — no unbounded lists anywhere in this subsystem.

Also track **aggregate-trade gap detection**: if a new `agg_id` is not `previous_agg_id + 1` (allowing for the `f`/`l` ranges), increment a `trade_gaps` counter and expose it in `StreamHealth`. Gaps mean the footprint for that bar is incomplete — the UI must be able to show that honestly.

### 2.5 `hub.py` — `MarketDataHub`
Singleton (same `__new__` pattern as `AutoTrader`) exposing:
- `async start()` / `async stop()` — called from `main.py` lifespan.
- `subscribe(symbol)` / `unsubscribe(symbol)` — dynamic, for symbols outside `FLOW_SYMBOLS` (e.g. user opens a new ticker).
- `get_state(symbol)` — the per-symbol `SymbolState` (trade buffer, book, bars, metrics cache).
- `register_listener(callback)` — the broadcaster (Phase 5) and the aggregators (Phase 3) attach here.
- `health()` → `dict[symbol, StreamHealth]`.
- **Reference counting** on dynamic subscriptions: unsubscribe only when the last consumer leaves, and never unsubscribe a symbol in `FLOW_SYMBOLS`.

### 2.6 `connectors/base.py` — future-proofing seam
Define an `ExchangeConnector` protocol: `name`, `normalize_symbol()`, `stream_names(symbol)`, `parse(raw) -> Trade | BookDelta | Kline`, `depth_snapshot(symbol)`, `tick_size(symbol)`. `binance_spot.py` implements it. **Implement only Binance.** This keeps the Bybit/OKX/Hyperliquid door open (as Flowsurface does) without paying for it now.

### 2.7 `main.py` wiring
In the existing `lifespan` context manager, after the DB inits and before `yield`: start the hub when `FLOW_ENABLED`. After `yield`: stop it. Wrap both in try/except and log — **a market-data failure must never prevent the API from booting.**

### 2.8 Acceptance Criteria
- [ ] With the backend running, logs show connection established and per-symbol first trade within 5 s.
- [ ] `test_orderbook_sync.py` replays `fixtures/depth_sequence.json` (snapshot + in-order diffs + one deliberately out-of-order diff) and asserts: correct book after in-order application, `DESYNCED` + resync triggered on the gap, zero-qty levels removed.
- [ ] `test_normalizer.py` replays `fixtures/aggtrades_btcusdt.json` and asserts side derivation, quote_qty math, and gap counting.
- [ ] Killing network for 20 s and restoring it: logs show backoff reconnect, book resync, `status` returns to `LIVE`. No unhandled exception, no memory growth.
- [ ] `Ctrl+C` shuts the server down in under 3 s with no pending-task warnings.
- [ ] Existing 59 tests still pass; API endpoints unaffected.
- [ ] Commit: `feat(flow): phase 2 — websocket ingestion`.

---

## PHASE 3 — Order Flow Aggregation Engines

**Goal:** turn the tick stream into the numbers a professional terminal shows. Pure functions where possible; every algorithm below is deterministic and unit-testable with fixture data.

### 3.1 Price bucketing (`footprint.py`)

Everything starts here; get it wrong and every panel is wrong.

- `tick_size` comes from `exchangeInfo` `PRICE_FILTER.tickSize` for the symbol (cached; refresh daily).
- `tick_group = tick_size × FLOW_TICK_GROUP_MULTIPLIER` (UI may send a per-request override).
- Bucket of a trade price `p`: `bucket = floor(p / tick_group) × tick_group`, rounded to the symbol's price precision to kill floating-point drift. **Use `decimal.Decimal` or integer-tick arithmetic for the bucketing itself**, then convert to float for transport. Do not accumulate float error across 50k trades.
- Sensible default multipliers so BTC does not render 100 000 rows: BTCUSDT `tickSize` is 0.01 → default UI grouping **10.0** (multiplier 1000); ETHUSDT → **1.0**; SOLUSDT → **0.1**; BNBUSDT → **0.1**; XRPUSDT → **0.0001**. Expose a grouping selector in the UI with presets `1× 5× 10× 25× 50× 100×` relative to these defaults.

### 3.2 Footprint bars

- Bar key: `open_time = floor(trade.ts / interval_ms) × interval_ms`.
- On each trade: find/create bar, find/create cell at the price bucket, then `buy_volume += qty` if `side == "BUY"` else `sell_volume += qty`; update `trades`, bar OHLC, bar `volume`, running `delta`, `max_delta`, `min_delta`.
- On bar rollover (new `open_time`, or `kline_1m` reports `x: true`): mark `is_closed`, compute the derived studies below once, push to the closed-bar ring buffer, emit a `bar_closed` event.
- Keep `FLOW_FOOTPRINT_BARS` bars per interval per symbol.
- **Cold start**: on subscribe, backfill closed bars from REST `aggTrades` (`GET /api/v3/aggTrades?symbol=&startTime=&endTime=&limit=1000`, paginated) for the last N bars of the smallest interval — cap the backfill at ~10 000 trades per symbol to stay inside the REST weight budget, and mark backfilled bars `source: "REST_BACKFILL"`. If backfill is unavailable, start with live bars only and mark earlier bars absent rather than fabricating them.

### 3.3 Derived studies per bar

**Diagonal imbalance** (the industry-standard footprint imbalance, and what Flowsurface calls its imbalance study):
- Compare `buy_volume` at price level `i` against `sell_volume` at level `i − 1` (one bucket lower).
- `buy_imbalance[i] = buy_volume[i] >= FLOW_IMBALANCE_RATIO × sell_volume[i−1]` and `buy_volume[i] >= FLOW_IMBALANCE_MIN_VOLUME`.
- `sell_imbalance[i] = sell_volume[i] >= FLOW_IMBALANCE_RATIO × buy_volume[i+1]` and `>= min volume`.
- Zero-denominator rule: treat `0` as imbalanced **only if** the numerator clears `FLOW_IMBALANCE_MIN_VOLUME`; otherwise not imbalanced. Document this — it is the classic source of a wall of false imbalances on thin levels.

**Stacked imbalance:** ≥ `FLOW_STACKED_IMBALANCE_MIN` consecutive price buckets with the same-direction imbalance → record `[low, high]` zone. These are the high-value institutional-interest zones and get the strongest visual treatment.

**POC / Value Area** (per bar and for the profile):
1. `poc_price` = bucket with max `total_volume` (tie → closest to the bar's VWAP).
2. Value area: start with `va_volume = poc_volume`; repeatedly compare the *sum of the two buckets above* the current VA top with the *sum of the two buckets below* the current VA bottom; add the larger pair and its volume; stop when `va_volume >= FLOW_VALUE_AREA_PCT × total_volume`. `vah` = top bucket, `val` = bottom bucket. (This is the standard two-above/two-below Market Profile expansion — implement exactly this, not a percentile shortcut.)

**Naked / unfilled POC:** a closed bar's `poc_price` that no *later* bar's `[low, high]` range has touched. Maintain a per-symbol list; on each new bar, remove any naked POC the new bar traded through. Expose the surviving list in `VolumeProfileSnapshot.naked_pocs`.

**Absorption:** flag `SELL_ABSORBED` when, in one bar, `sell_volume` is large (bar in the top quartile of the last 50 bars by volume) **and** `delta` is strongly negative (`delta_percent <= −0.25`) **but** the bar closes in the upper third of its range (`(close − low) / (high − low) >= 0.66`). Mirror for `BUY_ABSORBED`. In plain words: aggressive sellers were fully absorbed by resting bids and price refused to fall. Emit `None` when the bar has too little volume to judge.

### 3.4 `delta_engine.py`

- **Bar delta** = Σ cell deltas.
- **CVD (cumulative volume delta)**: running sum of trade-level delta, **anchored at session start = 00:00 UTC**. Also maintain a rolling-window CVD (last 1 h) for short-horizon signals. Reset/re-anchor is a config decision — document it in `FLOW_ARCHITECTURE.md`.
- **CVD slope**: least-squares slope of the last 30 CVD points, normalized per minute.
- **CVD divergence**:
  - `BEARISH` — price makes a higher high over the lookback (default 20 bars) while CVD makes a lower high.
  - `BULLISH` — price makes a lower low while CVD makes a higher low.
  - Require the price move to exceed a noise floor (e.g. 0.1 %) so flat chop does not spam divergences.
- **Aggression index** = (volume from prints ≥ whale threshold) / (total volume) over the last minute, clamped 0–1.
- **Buy/sell ratio** = rolling 1-minute `buy_volume / max(sell_volume, ε)`.
- **VWAP** = Σ(price × qty) / Σ(qty), session-anchored at 00:00 UTC, with ±1σ and ±2σ bands from the volume-weighted variance of price around VWAP.

### 3.5 `volume_profile.py`
- `SESSION` mode: all trades since 00:00 UTC (from the trade buffer; if the buffer is shorter than the session, mark `partial: true` — never silently under-report).
- `VISIBLE` mode: accepts `start_ts`/`end_ts` from the chart viewport.
- `FIXED_RANGE` mode: explicit ts range from a user selection.
- Output: levels with buy/sell split (this makes it a *delta profile*, strictly better than a plain volume profile), POC, VAH, VAL, naked POCs.

### 3.6 `dom_analytics.py`
- Ladder projection: group the book by `tick_group`, take N levels either side of mid, attach recent traded volume per price (from the trade buffer, last 60 s) so the ladder shows both **resting** and **executed** volume — this is what makes a ladder readable.
- `book_imbalance = (Σ bid_size − Σ ask_size) / (Σ bid_size + Σ ask_size)` over the top N levels; also report at N = 5 / 10 / 20 so the UI can show shallow vs. deep imbalance.
- **Walls**: level size ≥ `FLOW_WALL_MULTIPLIER` × median level size within the window; track `first_seen_ts` → `age_sec` and `persistence` (fraction of the last 30 s the wall was present). Persistent walls matter; flickering ones are usually spoofs and should be visually de-emphasized, not hidden.
- **Iceberg hint (heuristic, label it as such):** a level whose size is repeatedly consumed by trades and refilled to a similar size ≥ 3 times within 10 s. Expose as `iceberg_suspected: bool` with the refill count. Never present it as certainty — the reference terminals call this "possible iceberg activity" for a reason.

### 3.7 `tape_analytics.py`
- Enrich each trade: `size_bucket` by quote notional quartiles over the last 1000 prints (`S < p50 ≤ M < p90 ≤ L < p99 ≤ XL`), `is_whale` if `quote_qty >= FLOW_WHALE_NOTIONAL_USD` **or** above `FLOW_LARGE_PRINT_PERCENTILE`, `price_tick` vs previous print, `aggressive_streak`.
- Optional aggregation mode: merge consecutive same-price/same-side prints inside a 100 ms window into one tape row with a count badge (keeps a BTC tape readable).

### 3.8 `heatmap.py`
- Every `FLOW_HEATMAP_BIN_MS`, snapshot the grouped book into a `HeatmapFrame` (price → bid_size, ask_size) covering `mid ± K` buckets (default K = 60).
- Keep `FLOW_HEATMAP_WINDOW_SEC` of frames in a ring buffer.
- `max_size` for colour normalization = the 99th percentile of level sizes in the window (using the raw max lets one spoof wash out the whole picture).
- Output price axis bounds so the client can align the heatmap with the price chart exactly.

### 3.9 Threading / event-loop rules
- Aggregators are called **synchronously from the ingestion callback** and must be O(1)-ish per trade — dict/deque updates only. No sorting, no numpy allocation per trade.
- Per-bar derived studies (imbalance, VA, absorption) run **once on bar close**, plus a cheap incremental refresh for the forming bar at most `FLOW_BROADCAST_HZ` times per second.
- Anything heavier (profile recompute over 50k trades) runs in `run_in_executor` and is cached with a short TTL.

### 3.10 Acceptance Criteria
- [ ] `test_footprint.py`: a hand-built sequence of ~20 trades produces exactly the expected cells, bar delta, POC, VAH/VAL and imbalance flags (values asserted literally, not recomputed by the test).
- [ ] `test_delta_engine.py`: CVD accumulates correctly; a constructed higher-high/lower-high sequence yields `BEARISH` divergence; a flat sequence yields `None`.
- [ ] `test_volume_profile.py`: the two-above/two-below value-area algorithm matches a hand-computed example; naked POC list shrinks when a later bar trades through.
- [ ] `test_dom_analytics.py`: wall detection, imbalance signs (positive = bid-heavy), iceberg refill counting.
- [ ] `test_heatmap.py`: frame binning and percentile normalization.
- [ ] Measured: with 5 symbols live, backend CPU stays under ~25 % of one core. Record the number in the log.
- [ ] Commit: `feat(flow): phase 3 — aggregation engines`.

---

## PHASE 4 — REST Snapshot API

**Goal:** every panel can cold-start without waiting for a stream event, and can recover from a dropped socket.

New router in `backend/api/flow_routes.py`, registered from `backend/api/routes.py` (or directly in `main.py` — prefer `include_router` in `main.py` to keep `routes.py` from growing). Schemas in `backend/api/flow_schemas.py`. Reuse the existing `_get_cached`/`_set_cached` TTL-cache pattern.

| Method & path | Query params | Returns | Cache TTL |
|---|---|---|---|
| `GET /api/flow/status` | — | `{enabled, symbols: [...], health: {SYM: StreamHealth}}` | 1 s |
| `GET /api/flow/footprint` | `symbol`, `interval=1m`, `limit=60`, `tick_group?` | `{symbol, interval, tick_group, bars: FootprintBar[]}` | 1 s |
| `GET /api/flow/dom` | `symbol`, `levels=20`, `tick_group?` | `DomAnalytics` | 0.25 s |
| `GET /api/flow/tape` | `symbol`, `limit=200`, `min_notional?` | `{symbol, entries: TapeEntry[]}` | 0.25 s |
| `GET /api/flow/heatmap` | `symbol`, `window_sec?`, `tick_group?` | `HeatmapSnapshot` | 1 s |
| `GET /api/flow/volume-profile` | `symbol`, `mode=SESSION`, `start_ts?`, `end_ts?`, `tick_group?` | `VolumeProfileSnapshot` | 2 s |
| `GET /api/flow/cvd` | `symbol`, `interval=1m`, `limit=240` | `{symbol, points: CVDPoint[], vwap, bands}` | 1 s |
| `GET /api/flow/metrics` | `symbol` | `FlowMetrics` | 1 s |
| `POST /api/flow/subscribe` | body `{symbol}` | `{success, symbol, status}` — dynamic subscribe + immediate REST backfill kickoff | — |
| `POST /api/flow/unsubscribe` | body `{symbol}` | `{success, symbol}` — refcount-aware | — |
| `GET /api/flow/symbol-info` | `symbol` | `{tick_size, step_size, min_notional, price_precision, qty_precision, default_tick_group}` | 24 h |

**Conventions (match the existing codebase):**
- Unknown/unsubscribed symbol → `{"success": false, "error": "...", "subscribed": false}` with HTTP 200, *not* a 500 — the existing frontend `safeJson` pattern expects graceful shapes.
- `FLOW_ENABLED = False` → HTTP 503 `{"enabled": false, "reason": "..."}`.
- Symbol normalization reuses `_normalize_symbol` from `routes.py` (extract it to a shared util if importing creates a cycle).
- Every response carries `server_ts` (ms) so the client can compute display lag.

### 4.1 Acceptance Criteria
- [ ] `test_flow_routes.py` (FastAPI `TestClient`, hub mocked — **no live network in tests**) covers: happy path for each endpoint, disabled-flag 503, unknown-symbol graceful shape.
- [ ] Manual: every endpoint returns non-empty data within 10 s of backend start for `BTCUSDT`.
- [ ] `/api/flow/footprint?symbol=BTCUSDT&interval=1m&limit=5` returns bars whose `delta` equals the sum of their cells' deltas (assert this in the test).
- [ ] No existing endpoint's behaviour changed.
- [ ] Commit: `feat(flow): phase 4 — flow REST API`.

---

## PHASE 5 — Real-Time Broadcast Layer

**Goal:** push aggregated frames to the browser at a controlled rate, per symbol, without flooding.

### 5.1 Extend `backend/api/websocket.py` (keep existing events intact)

Add client→server events:
| Event | Payload | Behaviour |
|---|---|---|
| `flow:subscribe` | `{symbol, panels: ["dom","tape","footprint","heatmap","metrics"]}` | `sio.enter_room(sid, f"flow:{SYMBOL}")`, ensure hub subscription, immediately emit one snapshot of each requested panel to that `sid` |
| `flow:unsubscribe` | `{symbol}` | leave room; hub refcount decrement |
| `flow:settings` | `{symbol, tick_group, interval}` | per-sid render prefs; affects only what that client receives |

Server→client events (all emitted to room `flow:<SYMBOL>`):
| Event | Rate | Payload |
|---|---|---|
| `flow:tape` | `FLOW_TAPE_BROADCAST_HZ` (10/s) | `{symbol, entries: TapeEntry[]}` — **batched**, newest last |
| `flow:dom` | `FLOW_BROADCAST_HZ` (4/s) | `DomAnalytics` (levels already grouped + trimmed) |
| `flow:footprint` | 1/s + immediately on bar close | `{symbol, interval, bar: FootprintBar, is_closed}` — only the **forming/just-closed** bar, never the whole history |
| `flow:heatmap` | 1/s | latest `HeatmapFrame` only (client appends to its own ring buffer) |
| `flow:metrics` | `FLOW_BROADCAST_HZ` | `FlowMetrics` |
| `flow:health` | on change + every 5 s | `StreamHealth` |

### 5.2 Broadcast discipline (non-negotiable)
- **One broadcaster task per symbol**, driven by a timer, reading the latest state — *not* an emit per ingested trade. This decouples emit rate from market activity; a BTC volatility spike must not multiply socket traffic.
- **Skip empty frames.** If nothing changed since the last emit, do not emit.
- **No listeners → no work.** If a symbol's room is empty and the symbol is not in `FLOW_SYMBOLS`, pause its broadcaster entirely.
- Emit **floats rounded** to the symbol's precision before serializing. Full float64 repr triples payload size for no visual gain.
- Payload budget: target < 20 KB/s per symbol per client at `FLOW_BROADCAST_HZ = 4`. Measure and record it.
- Wrap every emit in try/except; a disconnected client must never kill the broadcaster task.

### 5.3 Acceptance Criteria
- [ ] Two browser tabs on the same symbol both receive updates; closing one does not disturb the other.
- [ ] Measured payload rate per symbol recorded in the log and under budget.
- [ ] Backend restarts while the UI is open → client reconnects automatically and re-subscribes (Phase 6 handles the client half; verify end-to-end here).
- [ ] Existing `portfolio_update` / `reasoning_event` still work on the current dashboard.
- [ ] Commit: `feat(flow): phase 5 — realtime broadcast`.

---

## PHASE 6 — Frontend Data Layer

**Goal:** a clean, typed, reconnect-safe client layer. No UI yet.

### 6.1 `frontend/src/lib/flow/flowApi.ts`
One fetcher per REST endpoint, following the existing `safeJson(res, fallback)` pattern in `lib/api.ts`. Never throw to the component; return a typed fallback plus an `ok` flag.

### 6.2 `frontend/src/lib/flow/useFlowSocket.ts`
- One **shared** `socket.io-client` instance for the whole app (module-level singleton; do not open a socket per panel). Connect to `NEXT_PUBLIC_API_URL`.
- API: `useFlowSocket(symbol, panels)` → `{status, lastEventTs}`; handles `flow:subscribe` on mount/symbol-change and `flow:unsubscribe` on unmount.
- Reconnect handling: on `connect`, re-send `flow:subscribe` for the active symbol **and re-hydrate from REST** (a socket gap means the client's forming bar and heatmap ring are stale).
- Expose connection status: `CONNECTING | LIVE | RECONNECTING | OFFLINE`.

### 6.3 `frontend/src/lib/flow/useFlowStore.ts`
- In-memory store (`useSyncExternalStore` or a small `useReducer` + context — **do not** add Redux/Zustand for this).
- Holds, per symbol: `bars` (map interval → array), `formingBar`, `tape` (ring, cap 500 in the UI), `dom`, `heatmapFrames` (ring, cap = window/bin), `metrics`, `profile`, `health`.
- **Patch semantics:** `flow:footprint` replaces the bar with a matching `open_time` or appends; `flow:tape` appends and trims; `flow:heatmap` pushes and trims; `flow:dom` / `flow:metrics` replace wholesale.
- **Hydrate-then-stream:** on symbol change, fetch REST snapshots first, render, *then* apply socket patches. Never show an empty panel while a socket warms up.
- **Render throttling:** panels must not re-render per event. Buffer incoming events and flush to React state on `requestAnimationFrame` (or a 100 ms timer for non-canvas panels). This is the difference between 60 fps and a locked tab.

### 6.4 `frontend/src/lib/flow/flowFormat.ts`
Price/qty/notional formatters honouring per-symbol precision, compact notation (`1.2K`, `3.4M`), IST timestamp formatting consistent with the existing terminal, delta colouring helper, tick-group rounding.

### 6.5 Acceptance Criteria
- [ ] A temporary debug page (or a `console.table` behind a dev flag) shows live metrics updating for `BTCUSDT`, then is removed before commit.
- [ ] `npm run lint` and `npm run build` clean; no `any` in the flow modules.
- [ ] Killing the backend flips status to `RECONNECTING` and recovers automatically on restart.
- [ ] Commit: `feat(flow): phase 6 — frontend data layer`.

---

## PHASE 7 — Terminal Panels

**Goal:** the panels themselves, each self-contained, each usable on its own before the workspace exists. Build them in the order below and check each into the same phase commit only after it renders live data.

Development route: create `frontend/src/app/terminal/page.tsx` early as a plain vertical stack of panels. The dockable grid arrives in Phase 8.

### Shared rules for every panel
- Wrapped in `PanelFrame` (title, symbol badge, settings gear, collapse, `StreamHealthBadge`).
- Explicit states: `LOADING` (skeleton), `EMPTY` (no data yet), `DISCONNECTED` (amber banner), `LIMITED` (degraded book mode). Never a blank box, never fabricated numbers.
- Palette strictly from the tokens in Appendix B.
- `memo()` + stable props. Canvas panels re-render on `requestAnimationFrame`, not on React state churn.
- Every canvas: handle `devicePixelRatio` for crisp text, `ResizeObserver` for container resize, and clean up listeners on unmount (copy the non-passive wheel-listener pattern from `CandlestickChart.tsx`).
- Keyboard/pointer parity with the existing chart: wheel = zoom, drag = pan, double-click = reset.

### 7.1 `FootprintChart.tsx` — the centrepiece

**Rendering:** Canvas 2D. Rationale: a 60-bar × 40-level footprint is 2 400 cells, each with two numbers plus background — that is ~10 000 SVG nodes at 1 fps updates. SVG cannot do it; canvas can do it at 60 fps.

**Layout per bar (column):**
- Column width scales with zoom; cells are `tick_group` tall on the shared price axis.
- **Cluster modes** (selector in the panel header): `BID_ASK` (default: `sell_volume × buy_volume` side by side), `DELTA` (single signed number per cell), `PROFILE` (horizontal bar per cell sized by total volume), `VOLUME` (total only).
- Cell background intensity ∝ `total_volume / max_cell_volume_in_view`.
- **Imbalance highlight:** buy imbalance → green left/edge marker on the buy number; sell imbalance → red on the sell number. **Stacked imbalance zones** get a bold bracket down the side of the column — these must be the most visually salient thing in the panel.
- **POC** per bar: subtle horizontal band. **Naked POCs**: dashed horizontal line extending right across the whole chart to the current price (this is the single most requested footprint study).
- Under each column: bar `delta` (green/red), `volume`, and `delta_percent`; optionally a mini delta bar.
- Candle outline (thin OHLC skeleton) behind the clusters so the price action stays readable.

**Interaction:** wheel zoom (price and time independently with modifier keys), drag pan, crosshair with a price/time readout, hover tooltip showing the exact cell (`price, buy, sell, delta, trades`), click-drag on the price axis to set a fixed-range volume profile, and a "go live" button when panned away from the right edge.

**Live bar:** the forming bar updates in place from `flow:footprint`; visually distinguish it (e.g. dimmed border) so a half-formed delta is never mistaken for a closed one.

**Tick-based intervals (stretch, mark as optional):** in addition to `1m/5m/15m`, allow bars that close every N aggregated trades. Flowsurface supports this; implement server-side as another "interval" key (`t500`, `t1000`) only if Phases 1–9 are complete and green.

### 7.2 `DOMLadder.tsx` — depth of market

**Rendering:** DOM/CSS grid (not canvas) — needs click targets and text selection. Virtualize if levels > 60.

**Columns, left to right:** `Sell Qty (my working orders)` · `Bid Size` · **`Price`** · `Ask Size` · `Buy Qty` · `Traded Volume @ Price` (last 60 s, buy/sell split).

- Horizontal bars behind bid/ask sizes scaled to the largest visible level; walls get a brighter, wider bar plus a size badge; `iceberg_suspected` gets a small icon with a tooltip that says *possible* iceberg.
- Centred on mid price with a live-centring toggle; clicking the price column re-centres.
- Best bid/ask row highlighted; spread shown in the header in ticks and bps.
- **Click-to-trade:** clicking the Buy column at a price stages a **limit** order at that price; clicking the market-order button stages a market order. Route through the existing `submitExchangeOrder` in `lib/api.ts` → `/api/exchange/order`. **Mandatory:** a confirmation step showing symbol, side, type, qty, price, notional, and the risk-gate verdict; no naked one-click execution in a demo build. Quantity comes from the same sizing control as the existing order panel.
- Cancel-all button wired to the existing `/api/exchange/cancel-all`.
- Working orders (from `/api/exchange/orders`) are rendered in the two outer columns at their price rows.

### 7.3 `TimeAndSales.tsx` — the tape
- Virtualized list (windowed rendering — 2 000 rows in the DOM will stutter), newest at top, auto-scroll with a pause-on-hover and a "resume" pill.
- Columns: `Time (IST, ms)` · `Price` · `Size` · `Notional` · side colour.
- Row background intensity by `size_bucket`; `is_whale` rows get a distinct accent + optional subtle flash on arrival.
- Filters in the header: minimum notional, side filter, aggregate-window toggle.
- A compact footer strip: 1-min buy vs sell volume bar, trade rate, aggression index.

### 7.4 `LiquidityHeatmap.tsx` — historical DOM
- Canvas. X = time bins (oldest left, now at right edge), Y = price buckets — **Y axis must be shared with the footprint chart** when both are docked.
- Colour: resting size → intensity, normalized by `max_size` (the 99th percentile). Bids and asks distinguished by hue, not just brightness.
- Overlay the traded price path as a thin line so absorption at a wall is visible at a glance.
- Persistent walls render as horizontal streaks — that is the whole point of the panel; verify visually against a known BTC session before calling this done.
- Controls: window (1/5/10/30 min), price grouping, colour intensity gamma.

### 7.5 `VolumeProfile.tsx`
- Horizontal histogram pinned to the right of the price axis; buy/sell split bars (delta profile), POC line, VAH/VAL band shading.
- Mode selector: `SESSION` / `VISIBLE RANGE` / `FIXED RANGE` (fixed range fed by the footprint chart's drag selection).
- Naked POC markers listed with their age.
- `partial: true` from the backend renders an explicit "partial session data" note.

### 7.6 `CVDPanel.tsx`
- Two synced sub-panes sharing the footprint's time axis: CVD line (session + rolling) and a per-bar delta histogram.
- VWAP with ±1σ/±2σ bands available as an overlay toggle on the price side.
- Divergence markers drawn at the bars where `divergence != null`, with a hover explanation of which high/low pair triggered it.
- Recharts is acceptable here (already a dependency, low data volume: ≤ 240 points). Do **not** use Recharts for the footprint or heatmap.

### 7.7 `FlowMetricsStrip.tsx`
A single dense horizontal strip above the panels — the "at a glance" bar:
`Price` · `Δ bar` · `CVD (session)` · `CVD slope` · `Buy/Sell 1m` · `Aggression` · `Book Imb (5/20)` · `Spread bps` · `Price vs Value` · `Nearest walls` · `Absorption flag` · `Stacked imbalance bias` · `Stream health`.
Each tile: value, colour-coded direction, a one-line tooltip explaining the metric in plain English (a judge or a new user must be able to read this panel).

### 7.8 `StreamHealthBadge.tsx`
`LIVE` (green, shows lag ms) / `DEGRADED` (amber: partial-book mode, or lag > 2 s, or recent gaps) / `DISCONNECTED` (red) / `DISABLED` (grey). Tooltip: streams connected, reconnect count, book resyncs, trade gaps, last event age. **This badge is what keeps the demo honest.**

### 7.9 Acceptance Criteria
- [ ] Each of the seven panels renders live `BTCUSDT` data on `/terminal`.
- [ ] Footprint numbers reconcile with the tape: pick a 1 m bar, sum the tape's buy volume in that minute, compare with the bar's `buy_volume` — must match within rounding. **Document this check in the log.**
- [ ] Ladder click-to-trade places a testnet limit order that appears in the existing Pending tab.
- [ ] Sustained 10 min on BTC+ETH: no memory growth beyond ~10 %, no dropped frames, tab stays responsive.
- [ ] Panels degrade correctly with the backend stopped.
- [ ] Lint + build clean; existing pages untouched.
- [ ] Commit: `feat(flow): phase 7 — terminal panels`.

---

## PHASE 8 — Workspace, Layout & Navigation

**Goal:** turn a stack of panels into a terminal.

### 8.1 Full-bleed layout
`AppLayout.tsx` currently constrains `main` to `max-w-7xl p-4 md:p-6`. A pro terminal needs the full viewport.
- Add an optional `fullBleed` mode: when active, `main` becomes `p-0 max-w-none h-[calc(100vh-56px)] overflow-hidden`.
- Trigger it from the terminal route (a layout segment for `/terminal`, or a context flag set by the page). **Do not** change the default for other routes.
- Sidebar auto-collapses on `/terminal` (respect the existing `volhelix:sidebar-toggle` custom event so `AppLayout` stays in sync).

### 8.2 `WorkspaceGrid.tsx`
- A resizable, dockable grid. **Prefer a hand-rolled CSS-grid + drag-handle implementation** over adding a layout dependency — the existing codebase hand-rolls its chart, and a new dependency is a new build risk. If a library is genuinely necessary, `react-resizable-panels` (MIT, tiny) is the only sanctioned option; record the decision in the log.
- Presets in the header:
  | Preset | Layout |
  |---|---|
  | **Order Flow** (default) | Footprint (large, left) · DOM ladder (right) · Tape (far right) · CVD (bottom-left) · Metrics strip (top) |
  | **Liquidity** | Heatmap (large) · DOM ladder · Tape · Volume profile |
  | **Execution** | Existing candlestick chart · DOM ladder · order entry · Positions dock |
  | **Analysis** | Footprint · Volume profile · CVD · Metrics |
- Per-panel: collapse, maximize (full-panel modal), close, settings popover.
- **Persist layout + per-panel settings (tick grouping, interval, cluster mode, filters) to `localStorage`** under a versioned key (`volhelix.workspace.v1`). Handle missing/corrupt state by falling back to the default preset — never crash on a stale layout.
- Symbol selector in the terminal header drives every panel at once, with an optional per-panel symbol lock (a pro-terminal nicety: DOM on ETH while the footprint stays on BTC).

### 8.3 Navigation
- Add `{ href: "/terminal", label: "Pro Terminal", icon: Activity, key: "terminal" }` to `navItems` in `Sidebar.tsx`. Place it directly under "Trading Terminal".
- Keep `/` (the classic dashboard) working and linked. **Only after Phase 11 sign-off**, optionally relabel `/` → "Classic Dashboard" and make `/terminal` the default landing. That swap is a one-line change and must be its own commit.

### 8.4 Acceptance Criteria
- [ ] Panels resize and reorder smoothly; layout survives a page refresh.
- [ ] All four presets render correctly at 1280 px, 1600 px and 1920 px widths.
- [ ] Below 1024 px the grid falls back to a single-column stacked view (a trading terminal need not be mobile-first, but it must not be broken).
- [ ] Classic dashboard and all other routes are visually unchanged.
- [ ] Commit: `feat(flow): phase 8 — workspace layout`.

---

## PHASE 9 — Strategy & Risk Integration

**Goal:** the bot sees what the trader sees. This is what makes the upgrade more than cosmetics — and it is also where the most damage can be done, so the guardrails are strict.

### 9.1 `backend/engine/flow_confluence.py`
A pure function: `evaluate_flow_confluence(symbol, metrics: FlowMetrics, bars: list[FootprintBar], side_bias: str) -> dict`.

Returns `{score: float (0..1), components: {...}, reasons: list[str], veto: bool, veto_reason: str|None}`.

**Components (weights inside the flow score, which itself is worth `FLOW_CONFLUENCE_WEIGHT` of the composite):**

| Component | Weight | Bullish condition | Bearish condition |
|---|---|---|---|
| CVD trend | 0.30 | `cvd_slope > 0` and session CVD rising | `cvd_slope < 0` |
| Stacked imbalance | 0.25 | recent buy-stacked zone below price (support) | sell-stacked zone above price |
| Absorption | 0.20 | `SELL_ABSORBED` present (sellers absorbed) | `BUY_ABSORBED` present |
| Book imbalance | 0.15 | `book_imbalance > +0.15` sustained ≥ 5 s | `< −0.15` sustained |
| Value/POC location | 0.10 | price reclaiming value from below / holding above VAL | rejecting from VAH |

**Vetoes (hard, independent of score):**
- `health.status != "LIVE"` → `veto = True`, reason `"Flow data not live"`. **A stale stream must never produce a trade signal.**
- `cvd_divergence` opposes the proposed side → veto.
- `spread_bps` above a configurable ceiling (default 5 bps for the majors) → veto (illiquid/disorderly conditions).
- Data insufficiency: fewer than 20 closed bars or a non-zero `trade_gaps` count in the evaluation window → veto.

### 9.2 Wiring into the existing gate
- `backend/engine/order_flow.py` → `evaluate_master_strategy_setup(...)` gains **one optional keyword argument** `flow: dict | None = None` (default `None`). When `None`, behaviour is byte-for-byte identical to today — this is what keeps the 59 existing tests green.
- When `flow` is provided and `FLOW_CONFLUENCE_ENABLED`:
  - Rescale the existing components from a 1.00 total to `1 − FLOW_CONFLUENCE_WEIGHT` (OB 0.40→0.30, FVG 0.30→0.225, GEX 0.20→0.15, R:R 0.10→0.075 at the 0.25 default), and add `flow.score × FLOW_CONFLUENCE_WEIGHT`.
  - **The 0.70 threshold does not change.** Do not lower it to compensate.
  - Append the flow `reasons` to the existing `reasons` list so the UI's scanner diagnostics explain themselves.
  - Any flow `veto` forces `is_valid = False` with `status_label = "FLOW VETO"`.
- `backend/engine/auto_trader.py` → in `_evaluate_single_symbol`, fetch `FlowMetrics` from the hub for the symbol (non-blocking, from cache) and pass it through. If the hub has no data for that symbol, pass `None` and proceed exactly as today.

### 9.3 Risk gate — do not touch
`backend/risk/risk_gate.py` and its 10 invariants stay **byte-identical**. Flow confluence can only ever *reduce* the set of trades taken. Write this sentence into `docs/FLOW_ARCHITECTURE.md`: *flow analytics may veto a trade, never authorize one that the risk gate would reject, and never enlarge a position.*

### 9.4 UI surfacing
- The existing scanner-diagnostic chips on the dashboard gain a flow sub-score and the flow reason lines (they already render `reasons`).
- The terminal shows a **Confluence** tile: composite score, per-component breakdown bars, veto state, and whether `FLOW_CONFLUENCE_ENABLED` is on.

### 9.5 Rollout
Ship Phase 9 with `FLOW_CONFLUENCE_ENABLED = False`. Run the scanner in shadow mode for at least one full session, logging what *would* have changed (log line: `SHADOW: {symbol} old_score={x} new_score={y} old_valid={a} new_valid={b}`). Only then flip the flag and record the decision in the log.

### 9.6 Acceptance Criteria
- [ ] `test_flow_confluence.py`: each component scored correctly in isolation; each veto triggers; a stale-health metrics object always vetoes.
- [ ] Calling `evaluate_master_strategy_setup` **without** `flow` produces identical output to the pre-change implementation (add a regression test asserting a known fixture's exact score).
- [ ] All 59 original tests pass unchanged.
- [ ] Shadow-mode log lines present for a full session.
- [ ] Risk gate file untouched (`git diff` proves it).
- [ ] Commit: `feat(flow): phase 9 — flow confluence integration`.

---

## PHASE 10 — Performance, Resilience & Limits

### 10.1 Backend
- Profile a 30-minute run on all 5 symbols. Record: CPU %, RSS, messages/sec, emit bytes/sec. **Budgets:** < 40 % of one core, < 600 MB RSS, stable (non-growing) after 10 minutes.
- Verify every buffer has a `maxlen`. A single unbounded list is an overnight OOM.
- REST weight audit: count the weight consumed per minute by depth snapshots, `aggTrades` backfill and `exchangeInfo`. Binance's documented IP budget is on the order of 1 200 requests/minute (see `docs/BINANCE_API_REFERENCE.md` §9) and depth snapshots at `limit=1000` are heavyweight. Stay under 20 % of budget in steady state; log the measured figure. Add a 429/418 handler: on 429 back off using the `Retry-After` header; on 418 (IP ban) stop REST calls for that symbol, mark health `DEGRADED`, and surface it in the UI.
- Optional persistence (`FLOW_PERSIST_BARS`): new `backend/store/flow_store.py` with an `aiosqlite` table `footprint_bars(symbol, interval, open_time, payload_json, PRIMARY KEY(symbol, interval, open_time))`, writing only **closed** bars, batched every 10 s. Default **off** — SQLite write amplification on every tick would be a self-inflicted wound.

### 10.2 Frontend
- Chrome DevTools Performance capture over 60 s on the default preset: target ≥ 50 fps, no long tasks > 100 ms, heap stable.
- Confirm every panel unsubscribes and cancels its rAF loop on unmount (mount/unmount the terminal 20 times, watch the listener count).
- Lazy-load heavy panels with `next/dynamic` and `ssr: false` (the existing `VolSurface.tsx` dynamic-import pattern is the template).

### 10.3 Failure matrix — verify each row by hand
| Failure | Required behaviour |
|---|---|
| Binance WS unreachable at boot | API boots; `/api/flow/status` reports `DISCONNECTED`; panels show the disconnected state; classic dashboard unaffected |
| WS drops mid-session | Auto-reconnect with backoff; book resync; UI returns to `LIVE` without a refresh |
| Book desync / gap | `DESYNCED` → resync; if repeated, downgrade to partial-book `LIMITED` mode |
| Backend restarted | Client reconnects, re-subscribes, re-hydrates from REST |
| Unknown symbol requested | Graceful `{success:false}`, no 500, no crashed task |
| `FLOW_ENABLED=false` | Whole subsystem dormant; `/terminal` shows a clear "order flow disabled" state; everything else normal |
| Clock drift | Existing `-1021` handling covers trading; flow uses server event timestamps, so display lag is computed from `E`/`T`, not local time alone |

### 10.4 Acceptance Criteria
- [ ] All measurements recorded in `docs/FLOW_UPGRADE_LOG.md`.
- [ ] Every row of the failure matrix manually verified and ticked.
- [ ] Commit: `feat(flow): phase 10 — hardening`.

---

## PHASE 11 — Documentation, Tests & Demo Readiness

### 11.1 Documentation
- `docs/FLOW_ARCHITECTURE.md`: the architecture diagram from §4, the data-flow narrative, every algorithm's definition (imbalance, value area, absorption, CVD divergence), every config key, the panel catalogue, and the degradation matrix.
- `docs/FLOW_CREDITS.md`: Flowsurface (GPL-3, Rust) credited as **design inspiration only, no code reuse**; OrderflowChart credited for the footprint data-shape convention; an explicit statement that VolHelix-AI remains MIT and contains no GPL-derived code.
- `docs/BINANCE_WEBSOCKET_STREAMS.md`: append the `aggTrade` payload spec, the diff-depth sync procedure (§2.3), connection limits and the 24 h rotation note.
- `README.md`: new section **"Institutional Order Flow Terminal"** — panel screenshots, the feature list, and a one-paragraph explanation of why tick-level flow beats bar-level SMC. Update the tech-stack table (add the websocket ingestion layer) and the architecture Mermaid diagram (add the `marketdata` subgraph). Update the test-count badge.
- `PRD.md` / `INNOVATION.md`: add the order flow engine as a differentiator — *the agents trade on the same tick-level microstructure the human sees, with a hard veto when the data is stale.*

### 11.2 Tests
Final tally target: **59 existing + ≥ 25 new**, all passing. Every new test must be deterministic and offline (fixtures only). Update the README badge to the real number.

### 11.3 Demo readiness (hackathon)
- A `scripts/flow_smoke_test.py` that boots the hub for 60 s on `BTCUSDT`, prints live metrics, and exits non-zero on failure — a 60-second pre-demo confidence check.
- Capture fresh screenshots into `docs/assets/` (`terminal_orderflow.png`, `terminal_heatmap.png`) and wire them into the README, following the existing `scripts/capture_real_screenshot.py` approach.
- Rehearse the 90-second demo path: open `/terminal` → point at a stacked imbalance → show the absorption flag → show the DOM wall → show the bot's confluence tile vetoing or approving → place a testnet order from the ladder.
- **Have an offline fallback.** If venue Wi-Fi blocks `wss://stream.binance.com`, a recorded fixture replay mode (`scripts/flow_replay.py` feeding the hub from `fixtures/`) saves the demo. Build it, label it unmistakably as `REPLAY` in the UI, and never let replay data reach the trading path.

### 11.4 Acceptance Criteria
- [ ] All docs written and accurate.
- [ ] Full test suite green; badge updated.
- [ ] Smoke test passes from a cold start.
- [ ] Screenshots captured; README updated.
- [ ] Commit: `feat(flow): phase 11 — docs, tests, demo`.
- [ ] Open a PR from `feat/order-flow-terminal` summarizing all 11 phases.

---

## 19. Known Defects To Fix Along The Way

These exist in the codebase **today**. Fix each in the phase indicated, with a test, in the same commit.

| # | Defect | Location | Fix in |
|---|---|---|---|
| 1 | **`/api/analytics/order-flow` is broken.** The endpoint builds bars as dynamically-typed objects with *attributes* (`type("Bar", (), {...})()`) and passes them to `analyze_order_flow`, which subscripts them (`b['high']`). This raises `TypeError` and the endpoint silently returns `{"success": false}` on every call. Note that `auto_trader` passes plain dicts and works — so the engine is fine, the endpoint is not | `backend/api/routes.py` ~line 1008 | Phase 4 |
| 2 | **Fabricated candle fallback.** `get_exchange_bars` returns invented OHLCV (`base_p = 76600.0` + a ramp) when the Binance call fails. A trading UI must never display fake prices | `backend/api/routes.py` ~line 615 | Phase 4 — return an explicit error state; the frontend shows "data unavailable" |
| 3 | **Equity-era leftovers in the crypto engine:** `current_price = 575.0` default, `± 0.25` absolute price buffers (meaningless at BTC scale), and a comment about "Alpaca bracket order constraints" | `backend/engine/order_flow.py` (`calculate_master_strategy_tp_sl`) | Phase 9 — replace absolute buffers with tick-relative ones (`n × tick_size`), drop the magic default, fix the comment |
| 4 | **`AlpacaClient = BinanceClient` alias** and the duplicated `/api/alpaca/*` route registrations still exist across the codebase | `backend/mcp/client.py`, `backend/api/routes.py`, `frontend/src/lib/api.ts` | Phase 11 — deprecate (log a warning) but **do not remove** during this upgrade; removal is its own PR with its own test pass |
| 5 | **Spot cannot short.** `evaluate_master_strategy_setup` can return `side = "SELL"` on a bearish bias, but spot testnet cannot open a short. Confirm the downstream path rejects or converts these; if it silently attempts a SELL with no inventory, that is a live bug | `backend/engine/auto_trader.py`, `backend/risk/risk_gate.py` | Phase 9 — verify and document the behaviour explicitly |
| 6 | **`VolHelixScheduler` is constructed but never started** in `main.py`; `TradingOrchestrator` runs only through `auto_trader` | `backend/main.py`, `backend/scheduler.py` | Phase 11 — document the intent (dead code vs. deliberate) in the log; no behaviour change |
| 7 | README claims a WebGL "3D volatility surface" and `$55,000–$75,000` BTC strike ladders — hard-coded ranges that will look wrong at a different BTC price | `frontend/src/app/volatility/page.tsx`, `README.md` | Phase 11 — make ranges relative to live spot |

---

## 20. Definition of Done

The upgrade is complete when **all** of the following hold:

1. `/terminal` renders seven live panels driven by real Binance websocket data, with sub-second updates.
2. Footprint numbers reconcile against the raw tape for a sampled bar (documented check).
3. Diff-depth book sync is implemented with gap detection, automatic resync and a partial-book degradation path.
4. The DOM ladder can stage and place a testnet order through the existing risk-gated execution path, with confirmation.
5. Layouts persist across refresh; four presets work at 1280/1600/1920 px.
6. `FlowMetrics` reaches the auto-trader; flow confluence can veto a trade; the 10 risk invariants are unchanged; the 0.70 gate is unchanged.
7. Stale or disconnected market data can never produce a trade signal (hard veto) and is always visible in the UI.
8. ≥ 84 tests pass; lint and production build are clean.
9. All seven known defects in §19 are fixed or explicitly documented as deferred with a reason.
10. Docs and README updated; screenshots captured; smoke test and replay fallback exist.
11. Every phase has its own commit and its own log entry.

---

## 21. Guardrails — Never Do These

1. **Never copy GPL-3 code** (Flowsurface or any fork) into this MIT repository. Inspiration only.
2. **Never add Rust, a desktop shell, or a second frontend framework.**
3. **Never use testnet for market data.** Testnet order books are thin and synthetic; the footprint would be meaningless. Market data = production, trading = testnet. That split already exists in `BinanceClient` — preserve it.
4. **Never fabricate market data** as a fallback. Empty + honest beats populated + false.
5. **Never block the FastAPI event loop.** All blocking REST goes through `run_in_executor`; all aggregation stays O(1) per tick.
6. **Never emit per tick to the browser.** Fixed-rate broadcasters only.
7. **Never weaken the risk gate**, lower the 0.70 confluence threshold, or let a flow signal increase position size.
8. **Never let a market-data failure break the API, the classic dashboard, or the Position Guardian.**
9. **Never refactor `page.tsx`, `routes.py` or `auto_trader.py` wholesale.** Additive changes at the named hook points only.
10. **Never leave an unbounded buffer, an uncancelled task, or an unhandled `asyncio` exception.**
11. **Never commit secrets.** No new keys are needed; public market streams are unauthenticated.
12. **Never mark a phase complete with a failing test or a red build.**

---

## Appendix A — Binance Spot Stream Reference (for this feature)

> Extends `docs/BINANCE_WEBSOCKET_STREAMS.md`, which already covers miniticker / kline / partial-depth / trade. Verify every figure below against the live Binance docs during Phase 2 — endpoints and limits change.

**Base:** `wss://stream.binance.com:9443` (port 443 also valid). Raw single stream: `/ws/<streamName>`. Combined: `/stream?streams=<a>/<b>/<c>` — combined payloads are wrapped as `{"stream": "<name>", "data": {...}}`.

**`<symbol>@aggTrade`** — one message per aggregated trade:
| Field | Meaning |
|---|---|
| `e` | `"aggTrade"` |
| `E` | event time (ms) |
| `s` | symbol |
| `a` | aggregate trade id — **monotonic; use for gap detection** |
| `p` | price (string) |
| `q` | quantity (string, base asset) |
| `f` / `l` | first / last underlying trade id |
| `T` | trade time (ms) — **use this, not `E`, for bar bucketing** |
| `m` | **is the buyer the market maker** → `true` ⇒ aggressor was the SELLER |

**`<symbol>@depth@100ms`** — diff depth: `U` (first update id), `u` (final update id), `b` (bid deltas), `a` (ask deltas). Quantity `0` = delete level. Sync procedure in §2.3 — follow it exactly.

**`<symbol>@depth<5|10|20>@100ms`** — partial book: `lastUpdateId`, `bids`, `asks`. Self-contained; no snapshot, no sync, no gap risk. Use for the ladder.

**`<symbol>@kline_<interval>`** — `k.t` (open time), `k.T` (close time), `k.o/h/l/c/v`, `k.n` (trade count), `k.x` (**is closed**), `k.q` (quote volume), `k.V`/`k.Q` (taker buy base/quote volume — a free cross-check on your computed delta: `taker_buy_volume ≈ Σ buy_volume` for the bar; **add this as an assertion in the footprint test**).

**REST helpers:** `GET /api/v3/depth?symbol=&limit=1000` (snapshot for sync — heavy weight, rate-limit it), `GET /api/v3/aggTrades?symbol=&startTime=&endTime=&limit=1000` (backfill, paginated), `GET /api/v3/exchangeInfo?symbol=` (tickSize / stepSize / minNotional).

**Connection limits to respect:** ~1 024 streams per connection (chunk at 200); 5 inbound control messages per second (pace SUBSCRIBE frames); connections are closed by the server at the 24-hour mark (rotate proactively at 23 h); the server sends ping frames every few minutes and expects timely pongs (the library handles this — verify in the installed version). Public market streams need **no API key**.

---

## Appendix B — Design Tokens

Extend `frontend/src/app/globals.css`; **do not invent a new palette.** Existing tokens (verified in the repo):

| Token | Hex | Use |
|---|---|---|
| Background | `#121214` | app background |
| Panel | `#18191f` | `.bybit-panel` |
| Panel header | `#1c1d22` | `.bybit-panel-header` |
| Border | `#26282f` | all dividers |
| Accent (gold) | `#f7a600` | brand, active states, POC |
| Buy / long | `#20b26c` | (already in `globals.css` gradients) |
| Text primary | `#f5f5f5` | |

Add for order flow:
| New token | Suggested | Use |
|---|---|---|
| `--flow-sell` | `#ef454a` | sell/ask side (match the existing red already used in `page.tsx` for asks) |
| `--flow-buy-dim` / `--flow-sell-dim` | 20 % alpha of the above | cell backgrounds scaled by volume |
| `--flow-imbalance-buy` / `--flow-imbalance-sell` | brighter buy/sell | imbalance markers |
| `--flow-poc` | `#f7a600` | POC line/band |
| `--flow-value-area` | `rgba(247,166,0,0.10)` | VAH–VAL shading |
| `--flow-naked-poc` | dashed `#f7a600` @ 60 % | unfilled POC lines |
| `--flow-wall` | `#7b61ff` | liquidity walls (deliberately *not* red/green — a wall is neutral until traded) |
| `--flow-heat-0..5` | dark→bright ramp | heatmap intensity (must stay legible on `#121214`) |
| `--flow-whale` | `#f7a600` @ 25 % bg | whale prints in the tape |

Typography: tabular numerals everywhere (`font-variant-numeric: tabular-nums`) — non-aligned digits in a ladder are unreadable. Mono font for all prices and sizes.

---

## Appendix C — Glossary (write this into the UI tooltips too)

| Term | Definition as implemented here |
|---|---|
| **Aggressor side** | The side that crossed the spread. Binance `m=false` → buy aggressor; `m=true` → sell aggressor |
| **Delta** | Aggressor buy volume − aggressor sell volume, at a price level or over a bar |
| **CVD** | Cumulative volume delta, session-anchored at 00:00 UTC |
| **Footprint / cluster chart** | A candle split into price buckets, each showing buy vs. sell volume |
| **Diagonal imbalance** | Buy volume at price P ≥ ratio × sell volume at P−1 tick (or the mirror). Default ratio 3.0 |
| **Stacked imbalance** | ≥ 3 consecutive imbalanced buckets in the same direction — an institutional-interest zone |
| **POC** | Point of Control: the price bucket with the most traded volume |
| **VAH / VAL** | Value Area High/Low: the bounds containing 70 % of volume around the POC |
| **Naked POC** | A prior bar's POC that price has not traded back through — a magnet level |
| **Absorption** | Heavy aggressive volume in one direction that fails to move price — resting liquidity absorbed it |
| **Liquidity wall** | A resting book level far larger than its neighbours (≥ 5× median) |
| **Iceberg (suspected)** | A level repeatedly consumed and refilled — a hint, never a certainty |
| **Book imbalance** | (bid depth − ask depth) / total depth over the top N levels, −1…+1 |
| **VWAP** | Volume-weighted average price, session-anchored, with volume-weighted σ bands |

---

## Appendix D — Deliberately Deferred (do not build now)

Each is a clean extension of the seams built above. Record them in `docs/FLOW_ARCHITECTURE.md` as "future work" so the architecture choices are justified.

| Item | Seam it plugs into |
|---|---|
| Bybit / OKX / Hyperliquid connectors | `marketdata/connectors/base.py` protocol |
| Binance **futures** streams (funding, open interest, liquidations, `forceOrder`) | a second connector + extra stream types |
| Tick-based and volume-based bar intervals | another interval key in the footprint engine |
| Bar replay / session playback (tyumex-style) | the replay script from Phase 11.3, promoted to a UI mode |
| Historical footprint persistence + backtesting on stored flow | `store/flow_store.py` (`FLOW_PERSIST_BARS`) |
| Options/GEX confluence | the existing `gamma_profile` parameter, currently always `None` |
| Alerts (wall appears, stacked imbalance, absorption, CVD divergence) | a listener on the hub + a new socket event |
| Server-side canvas pre-rendering / binary (msgpack) transport | only if payload budgets are ever exceeded |

---

*End of Upgrade_Plan.md — see `ANTIGRAVITY_SETUP.md` for the human-side setup steps.*
