# Upgrade verification - 2026-11-07

The combined repair at `207d6cc` addressed C1, I1-I2, I4-I5, M1-M2 and the
sequential I3 cases from the whole-branch review of `2bba0c5`. The current
commit addresses the two I3 concurrency findings from the independent scoped
re-review. Independent R1/R2 review, push/main integration and production-ref
verification remain controller-owned delivery gates.

Prior evidence is preserved in the dated [Task 9 record](artifacts/verification/task-9-verification-history.md),
[Task 9 summary](artifacts/verification/task-9-summary.json), and
[Task 8B record](artifacts/verification/task-8b-verification-history.md).
Their original results, image identifiers and public observations are historical.
The new [repair summary](artifacts/verification/final-repair-summary.json) records
these repairs and current limitations separately.

## Repairs and meaningful regression coverage

| Finding | Result and boundaries |
|---|---|
| C1 - lost scanner flow veto | Scanner and fresh Spot execution context resolve the market-owned shared hub. Enabled missing, warming, stale, disconnected or failed reads veto entries. Real strategy/risk regressions exercise scan-to-dispatch and LIVE-to-STALE transition. Disabled shadow behavior, exit eligibility, 0.70 threshold and $200 sizing remain. No new streams or per-evaluation hubs. |
| I1 - historical strategy records | All six former persisted strategy values retain their identities; mixed history/open/pending rows and guardian processing stay readable. No obsolete strategy generation restored. |
| I2 - fee-adjusted close preview | Server resolves the tracked position and shares quantity/filter rules with execution. Net0.9999SOL previews0.99 executable and0.0099 retained. Entry quantities remain strict; dust is retained; unknown actual commissions fail closed. Preview never cancels or submits. Confirmed pending entries cancel/reconcile before sizing final exposure. |
| I3 - lost close response | Confirmation carries one durable close ID. Completed and terminal partial attempts remain queryable. UI recovery queries the original market/ID through reload and market switch. Bare 404 and account mismatch remain uncertain. A close call retains its selected ID across awaits and replays the original outcome after concurrent completion. The SQLite reservation transaction binds the ID to one tracked trade per market and pinned account, including completed and local no-dispatch outcomes. No-dispatch proof releases an active ID only when no dispatch claim exists. |
| I4 - dynamic holdings valuation | Eligible non-watchlist Spot USDT holdings use verified production metadata/tickers in common snapshots. Outages/missing prices preserve stale recorded exposure; genuine emptiness stays empty. Wallet holdings are not promoted to tracked trades; no catalog-wide flow subscriptions. |
| I5 - subcent strategy prices | Real OHLC structure retains price precision. Both execution adapters and scanner require actual PRICE_FILTER tick metadata; structural buffers and rounding use that tick, with positive correctly directed long/short protection. Missing/nonfinite price and missing execution tick fail honestly; no575 fallback. Strategy weights and0.70 threshold remain. Tick-correct R:R changes one old fixture score from0.85 to0.90; disabled flow matches the same-tick bar-only baseline. |
| M1/M2 | Header displays normalized buying_power as Testnet available USDT, preserving zero. Four aggregate whitespace errors removed. |

New deterministic tests are `test_final_flow_contract.py`,
`test_legacy_strategy_records.py`, `test_tracked_close_contract.py`,
`test_dynamic_position_values.py`, `test_subcent_strategy_contract.py` and
`frontend/tests/final-close-contract.spec.ts`. Each reported behavior was first
reproduced failing. Focused backend groups passed144 and19 tests; the query-only
browser group passed6. Real strategy and real OHLC/protection logic are used for
C1/I5; exchange interactions are explicit fixtures. The risk gate file is
unchanged by this repair wave.

The November 7 `test_close_identity_races.py` regressions select the two actual
concurrent schedules reported in review. They also cover generated IDs, newer
generations, competing entry claims and stale sizing. The cases first failed
with duplicate orders, duplicated ledger reductions, or invalid reuse of a
reserved ID or newer generation. The 106 focused tests passed with the final fix.

## Verification gates

Commands run in the managed worktree root, or `frontend/` for npm/Playwright.
Shared Python runtime was `D:/Projects/VolHelix-AI/env/Scripts/python.exe`;
no private environment or database was copied. The suite prohibits unexpected
network access and SQLite writes outside temporary test directories. Credentials
were blanked in the backend verification process; no autonomous loops started.

| Date | Gate | Actual result |
|---|---|---|
| Nov1 | Bare-root `python -m pytest -q` | 377 passed,2 existing SDK deprecation warnings,91.27s |
| Nov1 | Full `npx playwright test` | 65 passed,2.0m; fixture HTTP and local Socket.IO only |
| Nov6 | `npm run lint` after Zod patch | exit0 |
| Nov6 | `npx tsc --noEmit` after generated files stabilized | exit0 |
| Nov6 | `npm run build` | exit0; Next16.4.3 compile/TypeScript/static8pages/all five application routes |
| Nov6 | Focused close/header browser and visual capture | 6 passed; final realistic base-fee capture1passed |
| Nov6 | `npm audit --json --fetch-timeout=15000 --fetch-retries=0` | exit1;8 moderate affected package entries from one development-toolchain advisory;0high/critical |
| Nov6 | `npm audit --omit=dev --json` | exit0;0 vulnerabilities |
| Nov6 | Backend Docker build/import | build exit0; network-disabled import exit0,ASGI callable,only MainThread |
| Nov6 | Backend Docker isolated suite | 377 passed, 2 existing SDK warnings, 39.78s; `--network none`, temporary ledgers |
| Nov6 | Frontend Docker build/artifact | build exit0; network-disabled artifact check exit0, Node22.23.4, Next16.4.3, nonempty build ID and all five app routes |
| Nov6 | Aggregate `git diff 5d07651 --check` | exit0 |
| Nov7 | I3 concurrency, lifecycle, close intent and fee regressions | 106 passed, 2 SDK deprecation warnings, 10.26s |
| Nov7 | Bare-root `python -m pytest -q` | 383 passed, 2 SDK deprecation warnings, 47.52s |
| Nov7 | Backend Docker rebuild/import | build exit 0; network-disabled import exit 0, callable ASGI and MainThread only |
| Nov7 | Rebuilt backend Docker isolated suite | 383 passed, 3 SDK deprecation warnings, 49.64s, network disabled |

The Nov1 backend suite and Nov6 backend image results cover the combined repair
before the I3 concurrency fix. The 65 fixture browser tests, lint, build,
TypeScript and frontend image checks cover the frontend used with the November 7
backend repair.
Standalone TypeScript initially raced `.next-e2e` generated-file cleanup when
run concurrently with browser startup; sequential verification passed without
removing valid config. Browser captures can log expected local socket connection
failures where the fixture deliberately lacks a socket server; this is not a
claim of a silent console.

The labelled [tracked-close confirmation](artifacts/ui/final-repair/tracked-close-preview.png)
was visually inspected: executable0.99, retained0.0099, original identity and
zero available balance are legible. It is an offline fixture, not live-account
proof. Historical Task8B PNG/JSON captures remain unchanged.

Scratch logs are `tmp/final-full-backend.log`, `final-full-browser.log`,
`final-lint-post-zod.log`, `final-typescript-post-build.log`, `final-build.log`,
`final-audit-post-zod.json`, `final-audit-production.json`,
`final-backend-docker.log`, `final-backend-image-check.log`,
`final-backend-image-pytest.log`, `final-frontend-docker-retry.log`,
`final-frontend-image-check.log` and `final-close-capture.log`. Curated summary data
is tracked, not full log dumps.

November 7 logs are `tmp/close-races-red.log`, `close-races-boundary-red.log`,
`close-races-late-red.log`, `close-races-focused-final.log`,
`close-races-full-backend.log`, `close-races-backend-docker.log`,
`close-races-backend-image-check.log` and `close-races-backend-image-pytest.log`.

## Dependency audit limitation

The Nov1 audit reported17 affected package entries. The compatible development
Zod update4.5.4 to4.6.7 removes the high issue; only its lockfile entry changed.
The patched floor is4.6.6 in the [Zod advisory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5).

The fresh Nov6 audit reports8 moderate package entries from the single
[minimatch glob-pattern amplification advisory](https://github.com/advisories/GHSA-g3hv-75wg-m249),
whose current npm affected range is>=7.0.0,<11.0.1. Here minimatch10.2.6 belongs
to the TypeScript ESLint development dependency chain; the3.1.5 branch is no
longer flagged by current advisory metadata. npm metadata confirms10.2.6 is the
latest10.x and latest typescript-estree8.72.1 still requires^10.2.2. A forced
minimatch11 override or suggested eslint-config-next16.4.3 to15.5.29 downgrade
would cross compatibility boundaries. The controller explicitly retained the
compatible tooling and recorded the residual crafted-glob denial-of-service
risk in lint/build tooling below. Production-only audit0 does not mean full
audit0 or prove the entire application free of vulnerabilities.

Docker installation uses `npm ci --no-audit --no-fund` after an install-time
metadata stall. Explicit full and production audits remain separate visible
gates; TLS verification and tests are unchanged.

## External verification and runtime limits

Controller read-only public CLI checks on Nov6 for Spot and Futures both exited1
with ConnectTimeout (`tmp/final-public-spot-nov6.log`,
`tmp/final-public-futures-nov6.log`). This proves unavailable access from this
environment, not an exchange outage or geographic restriction. No current LIVE
claim is supported. Earlier Oct22 Futures LIVE and Oct24 failures remain dated
historical observations.

No actual exchange orders, authenticated account queries, autonomous VolHelix
service/guardian startup or deployment were used for verification. Testnet
account modes, real fees/partial fills and actual guardian execution remain
unverified. The guardian requires a running backend process; historical losses
before first observed equity are unknown. PnL remains gross with actual native
fees separate; net PnL is unavailable.

Docker Desktop was restarted under explicit user approval;
unrelated existing Supabase containers auto-restarted and were left untouched.
Current images are `volhelix-backend:close-race-20261107` and
`volhelix-frontend:final-repair-20261106`. The latter contains build ID
`OZ86gu8qkEglJ6xRMTJ5U`; exact image IDs are in the repair summary.
Project checks use explicit `--context default` and network-disabled disposable
containers without an application lifespan. Unlocked Python dependencies mean
future install reproducibility is not certified. The unchanged inherited rolling
window/book internals remain an explicit unverified extreme-load limitation.
No exhaustive runtime, security or production-readiness claim is made.

## Rulings carried from the execution ledger

All ten lines below are preserved verbatim and in order, including their stated
costs. The controller must carry these and any later rulings to final delivery.

- Ruling: Use managed isolated checkout and existing original Python runtime — authorized implementation permits reversible setup; original user files stay untouched — cost if wrong: environment-dependent tests must be rerun.
- Ruling: Do not repeat unsafe baseline suite until Task 1 isolates clients/stores — inspected lifecycle tests invoke trading routes — cost if wrong: delayed baseline evidence.
- Ruling: Implement persisted first-observed daily/session account-equity baseline for Spot drawdown where Binance lacks direct daily PnL, exposing coverage timestamp and retaining observed loss across deposits — functional risk gating cannot use fabricated0 or remain a permanent stub — cost if wrong: losses before monitoring began are unknown; must clearly disclose coverage and keep missing equity fail-closed.
- Ruling: Bring backward-compatible persisted market fields forward into Task4 submission path — reachable Futures orders must never be stored as default Spot — cost if wrong: Task5 may refine serialization, legacy records remain Spot. Task5 retains lifecycle/guardian/reconciliation ownership.
- Ruling: Split approved Task8 into sequential8A backend/runtime and8B visual/frontend-dependency review units — newly verified financial/runtime findings plus five-route polish exceed one coherent review surface — cost if wrong: one extra review handoff; no added product feature scope. Briefs task-8a-brief.md/task-8b-brief.md, both execute after Task7 review.
- Ruling: Add tracked frontend/vercel.json git.deploymentEnabled.main=false in8B — connectedVercelautoDeploymentwouldotherwiseviolatetheapprovedno-production-deployscopeonmainpush — costifwrong: automaticmainreleasesremaindisableduntiluserexplicitlyre-enables; branchpreviewsunchanged. OfficialVercelgitconfigurationdocsverified; actualprojectrootfrontendconfirmed viaCLI. Task8Bassignedguard, final9mustverifyproductionrefunchanged.
- Ruling: Include narrow sharedprice-gridprecisionfix in8B alongsideUIformatting — actualbackendbucketpriceswerewrong/zero, sofrontformattingalonecannotmeetapprovednew-pair/datahonestyrequirements — costifwrong:Decimalper-tickoverhead; requireO(1),boundedhelpers,targetedflowregressions/volumeconservation/fullbackendverification. No risk/executionchanges. Task8Bimplementerassigned.
- Ruling: Carry the unchanged rolling-window/book internals as an explicit baseline verification limitation rather than redesign them in the final repair wave — the reviewer established no incremental regression or concrete failing workload there, while the binding spec prohibits broad rewrites — cost if wrong: extreme-load memory bounds and per-tick work in inherited internals remain uncertified; do not claim exhaustive runtime or production readiness.
- Ruling: Retain the compatible ESLint/Next development toolchain and disclose the remaining minimatch advisory rather than force a major minimatch override or downgrade Next ESLint configuration — fresh Nov6 audit has 8 moderate development package entries for GHSA-g3hv-75wg-m249, current typescript-estree still requires vulnerable10.x, while production audit is0 and Zod high is patched — cost if wrong: lint/build tooling remains susceptible to the advisory with crafted glob inputs; do not claim a zero-vulnerability full audit.
- Ruling: Continue with a narrowly scoped I3 concurrency repair despite the workflow one-wave limit — the independent re-review proved duplicate exchange reductions and one acknowledgement applied to two trades, so parking these load-bearing defects or merging would contradict the authorized repair goal and financial-data guardrails — cost if wrong: one additional targeted repair and independent validation cycle; no reopening of the completed whole-branch audit.
