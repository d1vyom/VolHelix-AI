# VolHelix reliability, market discovery, and Futures upgrade

Date: 2026-10-20 (Asia/Kolkata)
Status: proposed design for review; implementation has not started.

## Outcome and constraints

Audit the complete application, fix reproducible defects, add searchable Binance
markets and separate Spot/Futures modes, and refine the existing charcoal and
amber interface. Use exchange terminal conventions without copying Binance or
Bybit assets or source. Preserve existing user files and commits.

The user confirmed USDT-margined perpetual Futures on testnet. This extends the
old specification's Spot-only scope, while preserving every guardrail in
Upgrade_Plan.md section 21: production market data, testnet execution, no invented
data, bounded resources, nonblocking API paths, and no weakened risk checks.
No production trading or deployment is part of this work.

## Approach

Recommended: incremental repairs and a separate Futures adapter behind explicit
market-aware interfaces. Retain the current framework, Spot adapter, and flow
engine. Add narrow integration hooks instead of rewriting page.tsx, routes.py,
or auto_trader.py.

An interface-only Futures toggle is insufficient because it could silently
submit Spot orders. A full terminal/backend rewrite adds unnecessary regression
risk and conflicts with the guardrails.

## Initial findings from source inspection

These findings need regression coverage; they are not yet repaired.

- Manual order submission catches exchange exceptions, then persists an order
  and reports success. Exchange rejection must never become a local fill.
- Manual order submission substitutes a 75000 price if the quote lacks a price.
  Missing or invalid market data must prevent execution.
- The manual route calls synchronous exchange methods inside an async handler.
  Move blocking work off the event loop.
- The manual order route does not visibly invoke the deterministic risk gate.
  All entry paths need equivalent enforced checks before dispatch.
- Header scan errors can show successful synchronization messages.
- Header and terminal maintain separate hard-coded five-pair selectors.
- Sidebar account display substitutes a 10000 balance for zero/missing values.
- Client tests instantiate the real exchange SDK before mocking operations,
  making nominal unit tests depend on network connectivity.

## Market discovery and selection

Fetch public Binance exchange metadata per market, filter active instruments,
and expose searchable symbol/base/quote fields. Initially focus on USDT Spot
pairs and USDT perpetual Futures. Do not treat public listing as proof that a
symbol is executable on testnet: validate execution metadata separately.

Use one shared selection model containing market and symbol across the header,
dashboard, chart, order ticket, and terminal. Search must support keyboard use,
empty results, loading, retry, and accessible labels. Cache metadata with bounded
expiry; debounce search and cancel stale requests.

Selecting a market invalidates stale quotes, orders, balances, and chart state.
Socket rooms, caches, and position identifiers include market so identical
symbols cannot mix Spot and Futures data. Limit active flow subscriptions;
do not subscribe the flow engine to every listed pair.

## Trading behavior

Spot keeps its current testnet integration. Futures uses a separate testnet
client and credentials and production public Futures data. Verify current
Binance API contracts in official documentation during implementation.

Initially support market and limit orders, one-way positions, and conservative
1x leverage. Treat unsupported account modes as explicit errors. Never silently
change account-wide margin or position settings.

Validate finite positive values, exchange filters, available funds/inventory,
and risk checks server-side. Enforce the existing 0.70 entry confluence threshold
and position/drawdown limits. Distinguish exits from entries so closing risk is
not accidentally blocked by entry-only conditions. Futures closes must be
reduce-only; Spot sells cannot create shorts.

Show market, testnet status, symbol, side, quantity, price/notional, and risk
verdict in confirmation before submission. Persist exchange acknowledgement,
actual filled quantity, and actual fill price; pending and partial fills remain
distinct from completed fills. Reconcile uncertain outcomes rather than
blindly retrying a potentially executed order.

Extend positions, pending orders, cancellation, history, and guardian handling
with explicit market identity. Futures must not be routed through Spot exits.
Credentials remain server-side; missing credentials produce an honest
unavailable state. Never submit real orders as an automated verification step.

## Interface

Keep the charcoal backgrounds, amber emphasis, typography, and VolHelix brand.
Create a consistent market bar with Spot/Futures buttons and searchable pairs,
a legible statistics strip, chart/workspace, order ticket, and positions dock.
Use restrained borders, aligned numbers, consistent spacing, and clear hierarchy.

Inspect all five routes: dashboard, terminal, volatility, audit, and history.
Check narrow mobile widths, tablet, and desktop; prevent page overflow, clipped
controls, obstructed dialogs, and unusable fixed sidebars. Keep panel-level
scrolling where dense market information needs it.

Provide visible keyboard focus, labelled icon controls, usable contrast,
reduced-motion support, and truthful loading/empty/error/stale states. Never
display synthetic balances, successful scan messages, or market values as
fallbacks.

## Verification and acceptance

1. Establish pytest, lint, TypeScript, and production-build baselines.
2. For each behavioral fix, reproduce it in a failing test, implement the narrow
   fix, then run the regression and relevant suite.
3. Test rejected orders, invalid numbers, missing quotes, partial fills,
   precision/filter failures, insufficient funds, market isolation, and
   cancel/close routing with mocked exchange responses.
4. Keep unit tests independent of credentials and network. Separate read-only
   live connectivity checks from deterministic tests.
5. Verify each page in a real browser, including search, switching markets,
   confirmation, errors, responsive layouts, keyboard navigation, and console
   errors. Browser smoke tests must not start autonomous trading.
6. Verify public exchange access separately. Record external limitations
   honestly; a build passing alone does not establish working trading.
7. Review diffs for secrets, accidental generated files, and guardrail
   violations. Record actual commands, results, and unresolved limitations.

## Delivery

Use meaningful, independently reviewable commits and push verified milestones
to GitHub, then integrate the verified result into main as requested. Preserve
the existing ahead-of-origin commit. Do not manipulate timestamps, author
identity, or manufacture 60-70 commits. GitHub controls contribution attribution.

Implementation planning follows approval of this written design.
