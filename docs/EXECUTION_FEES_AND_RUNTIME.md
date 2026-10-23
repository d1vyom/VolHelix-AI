# Actual execution fees and runtime readiness

Task 8A, 2026-10-22. Execution remains testnet; market data remains production.

## Quantity and fee contracts

`OrderResult.executed_qty` and `TradeRecord.executed_qty` are cumulative gross
exchange fills. `TradeRecord.closed_qty` is cumulative actual sold/reduced
quantity. `TradeRecord.proposal.qty` and tracked position `qty` are remaining
holdings. Spot subtracts verified base-asset commissions from gross holdings;
Futures commission assets never change contract quantity or signed direction.
An order response's compatibility `qty` remains gross executed quantity.

New acknowledgement fields are `base_asset`, `fees` (native-asset amount map),
and `fees_known`. Trade records expose `entry_fees`, `exit_fees`,
`exit_order_fees`, `exit_order_fees_known`, `fees_known` (entry coverage), and
`exit_fees_known` (aggregate exit coverage). Coverage is `true` for complete
actual details, `false` for unavailable/incomplete details, and `null` for old
records without this contract. Legacy scalar `commission` fields are retained
for deserialization compatibility; use the maps and coverage flags for display.

Fill details come from full acknowledgements or order-specific testnet account
trade queries (`symbol` + `orderId`, up to 1000 fills). The summed fill quantity
must cover the cumulative acknowledged execution. Missing, malformed, or larger
histories remain explicitly unknown. No wallet-balance subtraction, commission
rate estimate, or third-asset currency conversion is used. A separate fee query
failure preserves a valid acknowledgement and gross exposure; it never becomes
`NOT_DISPATCHED`. Spot further reductions wait for actual fee recovery.

Closes cancel and reconcile a still-resting entry before reducing its filled
holdings. Sell quantity rounds down to exchange quantity rules. Untradeable
remaining inventory stays open with `dust_qty` and `dust_reason`; it is never
recorded as sold, including tiny positive residuals. Replay, restart, partial
execution, terminal cancellation, and later commission recovery preserve the
same durable order identities and cumulative accounting.

`realized_pnl` and position `unrealized_pl` are gross price differences, with
`pnl_basis = "gross_price_difference_fees_separate"`. Actual fee amounts are
reported separately; `net_realized_pnl` remains `null`. Do not label these gross
metrics as net trading profit. Portfolio `daily_pnl`, `daily_pnl_pct`,
`total_pnl`, and `total_pnl_pct` are nullable when unknown; configured seed
capital is not an account profit baseline. `account_available` is false before
a verified account observation and after a read error. Retained observations
then require a stale/unavailable label; `daily_risk_available` stays false
without a daily observation.

Tracked `/api/market/positions` rows include gross execution, closed quantity,
fee maps/coverage, dust, and PnL basis. Trade/history records expose the full
fields above. Legacy quote/account aliases remain registered. Quote/account
failures return 503; missing bid/ask/spread are null. Failed signal reads have
`available: false`, null financial fields, and no fabricated bullish trend.

## Runtime and local configuration

Application lifespan owns guardian startup, scanner/guardian stop/join, and
notification cleanup. Importing the application starts no trading threads.
Trading notifications admit at most 32 queued or running application-loop tasks;
lifecycle shutdown closes admission, cancels and awaits the actual tasks through
their asynchronous cleanup. Generic logging writes only to console/rotating files,
without synchronous HTTP calls back into the API. History, audit, and the two
legacy caches retain at most 1000 entries; audit list aliases are preserved.
Existing sync legacy read endpoints run in FastAPI's thread pool.

`CORS_ORIGINS` is a comma-separated explicit allowlist, defaulting to the local
frontend on localhost/127.0.0.1:3000, shared with Socket.IO. Configure actual
origins for other environments; wildcard credentialed access is unsupported.
This is local configuration repair, not a production security certification.

Compose uses Settings' actual environment names and separate Futures credentials.
Backend Python 3.13 and frontend Node 22 images exclude environment files,
dependencies, caches, logs, scratch artifacts, and runtime databases from build
contexts. `/app/backend/data` uses the `backend_data` named volume for trade,
intent/risk, postmortem and optional flow databases. The frontend's
`BACKEND_URL=http://backend:8000` must be present at build and runtime because
Next rewrites are compiled. Browser Socket.IO uses the build argument
`NEXT_PUBLIC_SOCKET_URL` (local default http://localhost:8000); rebuild the
frontend after changing it. Runtime `NEXT_PUBLIC_*` assignments do not alter an
already compiled bundle. No credentials are build arguments.

The obsolete connectivity script is now an explicit read-only public Binance
CLI: `python scripts/test_mcp_connection.py --market spot --symbol SOLUSDT`.
It reads server time and price only, does not load environment files, does not
log credential prefixes, and does not verify authenticated execution. Root
pytest collection is scoped to `backend/tests`; script imports perform no I/O.

## Verification

- Focused RED/GREEN fee, lifecycle, outcome, runtime and script regressions.
- Final isolated bare-root `python -m pytest -q`: 313 passed, two existing SDK
  websocket deprecation warnings, 32.70 seconds.
- Task 8A review fixes (2026-10-23): same-amount terminal fee coverage recovery,
  residual-close replay, and notification cancellation cleanup regressions.
  Updated isolated bare-root suite: 318 passed, the same two SDK warnings,
  30.73 seconds. Both original independent review probes also pass.
- First full run exposed three older incomplete order fixtures; explicit actual
  zero-commission details/query responses repaired those fixtures while retaining
  their assertions. The no-network guard prevented external requests.
- Compose configuration validated using an empty env file and no interpolation.
- Current backend Docker image built; `docker run --rm --network none` import
  check confirmed only the main thread and no trading loop.
- Frontend Docker build was canceled after 10m33s without completing `npm ci`;
  its image is unverified. Final current frontend image validation follows
  Task 8B. The cause of the stalled dependency installation is unconfirmed.

No live orders, autonomous trading service startup, credential copying, deployment,
or frontend TSX/package edits were performed. Authenticated execution and hosted
production readiness are not established by these deterministic checks.
