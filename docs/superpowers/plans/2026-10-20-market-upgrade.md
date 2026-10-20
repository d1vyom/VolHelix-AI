# Reliability and Spot/Futures Market Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair verifiable defects, provide searchable Spot/USDT perpetual markets with testnet execution, and polish all five pages without changing VolHelix's theme.

**Architecture:** Preserve existing Spot behavior through narrow hooks, introducing a separate Futures client and explicit market identity. Centralize validated execution and market selection so UI, persistence, and guardian paths cannot disagree.

**Tech Stack:** Existing Python/FastAPI/Pydantic/SQLite, Next.js/React/TypeScript/Tailwind, Socket.IO, pytest; browser verification with Playwright.

**Spec:** `docs/superpowers/specs/2026-10-20-market-upgrade-design.md` (approved by the user on 2026-10-20).

## Global Constraints

- Production market data; testnet execution only; no production deployment.
- Preserve all `Upgrade_Plan.md` section 21 guardrails and existing user files/commits.
- No wholesale rewrite of `page.tsx`, `routes.py`, or `auto_trader.py`.
- Enforce the existing 0.70 entry confluence threshold and position/drawdown limits.
- Initially support market and limit orders, one-way positions, and conservative 1x leverage.
- Never silently change account-wide margin or position settings.
- Never submit real orders as an automated verification step.
- Meaningful commits with truthful timestamps; no manufactured contribution count.
- Before each behavioral change: failing regression, minimal fix, passing verification.
- Read `frontend/AGENTS.md` and installed Next.js guides before frontend implementation.

## Review Focus

- A timed-out order may already exist at Binance: reconcile by stable client ID, never blindly resubmit (Task 3).
- A Spot and Futures position can share a symbol and order number: preserve market-scoped identity (Tasks 4, 5).
- Rapid market switching can deliver stale HTTP/socket data: reject obsolete results (Tasks 6, 7).
- A partial fill followed by cancellation still leaves exposure: retain filled quantity and guardian coverage (Task 5).
- An upstream outage must not erase positions or stop protective exits: isolate data and lifecycle failures (Tasks 5, 8).

## File and interface map

- `backend/exchange/models.py`: `Market = Literal["spot", "futures"]`; `Instrument` with market, symbol, base_asset, quote_asset, status.
- `backend/exchange/registry.py`: `get_exchange_client(market: Market)` returns the existing Spot client or new Futures client. Default omitted market to Spot for legacy callers.
- `backend/exchange/catalog.py`: `async list_instruments(market: Market) -> list[Instrument]`; production metadata, bounded cache.
- `backend/exchange/execution.py`: `async preview_order(request: OrderRequest) -> OrderPreview`; `async submit_order(request: OrderRequest) -> OrderResult`. Server computes checks again at submission.
- `backend/exchange/schemas.py`: `OrderRequest`, `OrderPreview`, `OrderResult`; finite numeric inputs, explicit market/side/type, client_order_id, reduce_only, and actual execution fields.
- `backend/mcp/futures_client.py`: `BinanceFuturesClient`; same normalized quote/account/order interfaces as Spot, explicit Futures endpoints.
- `backend/api/market_routes.py`: catalog, preview, and narrowly scoped new endpoints; register in `backend/main.py`.
- `frontend/src/lib/market/MarketProvider.tsx`: `{market, symbol, setSelection}` shared React context.
- `frontend/src/components/market/MarketSelector.tsx`: accessible market controls and searchable instrument selection.
- Existing API, flow, trade/store, chart, and page files receive explicit market arguments and localized fixes.
- New tests live under `backend/tests/`; browser regressions under `frontend/tests/` with isolated configuration.

## Task 1: Make verification independent of accounts and persistent data

**Files:** `backend/tests/conftest.py`, `test_binance_client.py`, `test_order_lifecycle.py`, `test_auto_trader.py`; inspect remaining tests for external clients/stores.

- [ ] Add `test_suite_uses_temporary_trade_store`: assert database paths are under pytest's temporary directory and previous application records are absent.
- [ ] Add `test_exchange_fixture_never_contacts_network`: construct the client with the SDK constructor patched; assert no production/testnet network operation executes.
- [ ] Run the new tests individually; expect failure against current unisolated fixtures without invoking the unsafe lifecycle suite.
- [ ] Patch constructors before client creation, reset singleton/cache state per test, supply fake order responses, and redirect all test databases. Disable background guardian/scanning in API tests. Reject unexpected network calls.
- [ ] Run `.\env\Scripts\python.exe -m pytest backend/tests -q`; expect all tests to pass without keys or external connectivity.
- [ ] Commit and push `test: isolate exchange clients and trade databases`.

## Task 2: Repair Spot validation and false-success order paths

**Files:** new exchange schemas/execution module; `backend/api/routes.py`, `backend/mcp/client.py`, `backend/tests/test_order_submission.py`.

- [ ] Parameterize `test_rejected_order_is_not_persisted` across raised SDK errors and error-shaped results: assert non-2xx response, no saved trade, and no success event.
- [ ] Add `test_invalid_order_never_dispatches` for zero/negative/NaN/infinite quantities, unsupported side/type, missing limit price, and missing/zero price: assert rejection and zero exchange order calls.
- [ ] Run these tests; expect failures exposing current permissive behavior.
- [ ] Implement finite Pydantic validation and error propagation, remove invented prices/order IDs, and use `asyncio.to_thread` for synchronous exchange work. Persist actual acknowledgements/fills only.
- [ ] Run submission and existing lifecycle tests; require pending/partial/filled distinctions and correct base quantity for quote-sized orders.
- [ ] Commit and push `fix: reject invalid orders and preserve exchange failures`.

## Task 3: Enforce entry risk, confirmation, and retry reconciliation

**Files:** `backend/exchange/execution.py`, `schemas.py`, `backend/risk/risk_gate.py`, `backend/api/market_routes.py`, narrow order hook in `routes.py`; `backend/tests/test_execution_risk.py`.

- [ ] Add tests asserting confluence `0.69` rejects, `0.70` passes that check, capital above 2.5% NAV rejects, and daily drawdown at the existing gate boundary rejects. Supply otherwise-valid gate fixtures.
- [ ] Add `test_spot_sell_cannot_short`, `test_exit_uses_exit_checks`, `test_preview_cannot_bypass_submit_checks`, and `test_timeout_reconciles_client_order_id`: assert no blind retry or duplicate trade.
- [ ] Run focused tests and confirm failures before implementation.
- [ ] Implement `preview_order` and `submit_order`, reusing deterministic gate inputs and fresh server data. Apply Decimal exchange filter checks and fresh inventory/funds checks. Return explicit risk verdict; never trust a client-supplied approval.
- [ ] Bound reconciliation to one stable client order ID; report uncertain outcome when lookup cannot resolve it. Verify close requests cannot increase or reverse exposure.
- [ ] Run focused tests and full isolated suite; commit and push `fix: enforce execution risk and reconcile uncertain submissions`.

## Task 4: Add market catalog and Futures adapter

**Files:** new exchange models/registry/catalog, Futures client, market routes; `backend/config.py`, `.env.example`; `backend/tests/test_market_catalog.py`, `test_futures_client.py`.

- [ ] Verify current public and testnet API contracts in official Binance documentation. Record endpoint/SDK compatibility evidence without credentials.
- [ ] Add catalog tests: active USDT Spot/perpetual inclusion, halted/non-USDT/delivery exclusion, bounded TTL, and honest upstream errors.
- [ ] Add adapter tests asserting Futures trading uses testnet, public data uses production, missing Futures keys never falls back to Spot, and unsupported hedge mode/leverage is rejected.
- [ ] Run tests, observe failures, then implement the declared interfaces and separate `BINANCE_FUTURES_API_KEY` / `BINANCE_FUTURES_API_SECRET` settings.
- [ ] Validate testnet execution filters separately from public market discovery. Require 1x leverage; return an actionable setup error rather than silently modifying account settings.
- [ ] Verify quote, candle, depth, account, create/cancel/status, and reduce-only close mappings with fixtures. Run catalog/adapter tests; commit and push `feat: add searchable market catalog and testnet Futures adapter`.

## Task 5: Preserve market identity through the full order lifecycle

**Files:** `backend/models/trade.py`, `models/market.py`, `store/trade_log.py`, `api/routes.py`, `engine/auto_trader.py`, `exchange/execution.py`; lifecycle/guardian tests.

- [ ] Add `test_legacy_trade_defaults_to_spot`, `test_same_symbol_positions_are_market_isolated`, and `test_futures_exit_is_reduce_only`: assert compatible deserialization and correct adapter selection.
- [ ] Add partial-fill/cancel tests asserting remaining exposure survives cancellation and uses actual weighted fill price. Add outage tests asserting stored positions remain visible and another market's guardian still operates.
- [ ] Run regressions; expect missing-market/lifecycle behavior to fail.
- [ ] Persist market and exchange status with backward-compatible Spot defaults; use market/symbol/order identity for reconciliation. Extend pending, cancel, close, history, and guardian hooks without wholesale refactors.
- [ ] Remove locally simulated fills from exchange execution paths; any existing manual fill endpoint must reconcile exchange state or reject the operation.
- [ ] Run lifecycle, auto-trader, risk, and store tests. Commit and push `feat: reconcile market-aware positions and protective exits`.

## Task 6: Make order-flow data and transport market-aware

**Files:** `backend/marketdata/connectors/binance_futures.py`, `hub.py`, `orderbook.py`, `stream_manager.py`, `api/flow_routes.py`, `api/websocket.py`; matching flow tests.

- [ ] Add fixtures for Futures trade/depth messages and gap recovery using its documented sequence rules; assert Spot rules are preserved separately.
- [ ] Add `test_flow_state_is_market_scoped`, `test_subscription_limit_rejects_excess`, and `test_last_unsubscribe_stops_broadcaster`: assert no mixed snapshots, bounded symbol count, and task cancellation.
- [ ] Run focused tests to failure.
- [ ] Implement Futures connector using the existing connector protocol, market-aware hub state and rooms, and explicit market query/payload fields defaulting to Spot. Enforce a configurable maximum of 10 active on-demand symbols and release idle subscriptions.
- [ ] Preserve fixed broadcaster rates and buffer limits. Test reconnect, hydration, snapshot errors, shutdown, and isolation from classic API/guardian.
- [ ] Run all flow tests; commit and push `feat: isolate Spot and Futures order-flow streams`.

## Task 7: Connect shared search, market selection, and confirmed trading UI

**Files:** new MarketProvider/MarketSelector; `frontend/src/lib/api.ts`, `lib/types.ts`, `lib/flow/*`, `components/AppLayout.tsx`, `Header.tsx`, `CandlestickChart.tsx`, `flow/*`, `app/page.tsx`, `app/terminal/page.tsx`; `frontend/tests/markets.spec.ts`.

- [ ] Add mocked-browser regressions for symbol search by base/symbol, no matches, retry, keyboard selection, and Spot/Futures switching. Assert requests contain the selected market and old responses never replace new selection.
- [ ] Add `rejected order stays out of positions` and `confirmation shows risk verdict` scenarios. Assert required fields, disabled submit on failed risk checks, and no POST before confirmation.
- [ ] Run browser tests and observe missing controls/behaviors.
- [ ] Implement provider, selector, and market-aware API/socket/store contracts. Reset stale state on selection; abort obsolete requests; unsubscribe on unmount; remove duplicate hard-coded selectors.
- [ ] Connect quotes, charts, balances, orders, positions, history, and DOM order staging to the shared selection. Clearly display testnet and unavailable credentials/account modes.
- [ ] Run browser regressions, `npm run lint`, and `npm run build`; commit and push `feat: add searchable Spot and Futures trading workspace`.

## Task 8: Audit and polish all routes

**Files:** `AppLayout.tsx`, `Sidebar.tsx`, `Header.tsx`, `app/globals.css`, all five page modules and affected panels; `frontend/tests/navigation.spec.ts`.

- [ ] Capture baseline browser screenshots at 390, 768, and 1440px widths. Record concrete clipping/spacing/navigation defects before changing layout.
- [ ] Add regressions for zero balance remaining zero, unavailable balance showing unavailable, scan failures showing failure, and stale data not presented as live.
- [ ] Test keyboard navigation/dialog focus, no page-level horizontal overflow, mobile navigation, reduced motion, and panel scrolling.
- [ ] Apply localized charcoal/amber layout fixes, aligned statistics and controls, accessible labels/focus, and truthful status messages. Check volatility/audit/history for invented values or stale market assumptions.
- [ ] Inspect backend API, analytics, stores, agents, scheduler, startup/shutdown, and scripts for further reproducible defects; add a failing test before each behavioral repair. Track findings and evidence in `docs/UPGRADE_VERIFICATION.md`.
- [ ] Run affected tests and visually compare all routes; commit/push independently meaningful fixes, without artificial commit splitting.

## Task 9: Verify, review, and integrate

**Files:** `docs/UPGRADE_VERIFICATION.md`, `README.md`, `.env.example`; final reviewed implementation.

- [ ] Run the complete isolated backend suite, lint, production build/TypeScript, and browser regressions. Preserve exact results and limitations.
- [ ] Run read-only public Spot/Futures connectivity checks separately. Do not submit orders or start the autonomous trader. Report unavailable external access honestly.
- [ ] Review all changed execution paths, full branch diff including the pre-existing local commit, secrets/generated files, and every guardrail. Fix findings and rerun affected checks.
- [ ] Document setup, separate Futures credentials, supported account mode, testnet limitations, and actual verification results. Remove outdated claims of test counts/unsupported features.
- [ ] Push verified commits, integrate into main with no force push, and verify remote main matches the intended commit. Check for deployment automation before pushing main; keep production deployment outside scope.
- [ ] Deliver commit references, test outcomes, feature coverage, and any remaining externally blocked validation. Do not claim all possible bugs are eliminated.

## Plan self-review

The tasks cover the approved spec's trading, market discovery, UI, compatibility,
verification, and delivery requirements. The five review-focus cases have explicit
test owners. Work proceeds in dependency order; the UI consumes the API and
market identities established earlier. Execution method remains for user selection.
