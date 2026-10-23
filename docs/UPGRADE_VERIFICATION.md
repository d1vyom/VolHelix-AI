# Upgrade verification — 2026-10-24

Runtime verified: implementation commit `a77679d` on
`codex/market-upgrade-implementation`, managed isolated worktree. Task 9 changes
are documentation and curated evidence only. Tasks 1-8B passed their scoped
reviews. Task 9 review, fresh whole-branch review (including pre-existing
`e06ac14`), push/main integration and remote/deployment-ref checks remain the
controller's delivery gates. Production deployment remains outside scope.
The preceding [Task 8B repair and review evidence](artifacts/verification/task-8b-verification-history.md)
is preserved as a dated historical record; its screenshot link follows the new
archive location.

## Final checks

Commands run from the managed worktree root unless `frontend/` is specified.
The local interpreter was `D:/Projects/VolHelix-AI/env/Scripts/python.exe`
(Python 3.13.7); no environment, credentials or runtime database was copied from
the primary checkout. Local Node was 24.18.1. Root/frontend private dotenv count
and relevant inherited exchange/LLM credential count were both zero. Python
verification additionally blanked the named credential variables explicitly.

| Check | Command | Actual result |
|---|---|---|
| Complete backend, bare root | `D:/Projects/VolHelix-AI/env/Scripts/python.exe -m pytest -q` | 329 passed, 2 warnings, 53.09s |
| Lint, `frontend/` | `npm run lint` | exit 0, no lint diagnostics |
| TypeScript, `frontend/` | `npx tsc --noEmit` | exit 0 |
| Production build, `frontend/` | `npm run build` | exit 0; compile, TypeScript, 8 static pages and route generation successful |
| Complete browser regressions, `frontend/` | `npx playwright test` | 59 passed, 1.3m |
| Dependency audit, `frontend/` | `npm audit --json` | exit 0; 0 vulnerabilities, 769 dependencies counted |
| Backend Docker | `docker --context default build --progress=plain -f backend/Dockerfile -t volhelix-backend:verify-29ee136 .` | controller build exit 0; backend source unchanged through `a77679d` |
| Frontend Docker | `docker --context default build --progress=plain -f frontend/Dockerfile -t volhelix-frontend:verify-a77679d frontend` | controller build exit 0, including npm ci and Next build/export; Dockerfile default endpoint arguments |
| Backend image isolation | network-disabled `docker run --rm` importing `backend.main`, with blank exchange/Google credentials | exit 0; ASGI callable; only MainThread; no lifecycle/server started |
| Frontend image artifact | network-disabled `docker run --rm` reading Node/Next versions and `.next/BUILD_ID` | exit 0; Node 22.23.4, Next 16.4.3, nonempty build ID |

Backend warnings are the existing `python-binance` import of deprecated
`websockets.WebSocketClientProtocol` (twice). Image import also logs the retained
legacy `AlpacaClient` alias deprecation. These checks do not certify external
service availability or authenticated execution. Python dependencies are not
locked; the existing environment and the independently built image are separate
pieces of evidence, not a reproducibility guarantee for future installs.

Exact local logs are `tmp/task9-pytest.log`, `task9-lint.log`,
`task9-typescript.log`, `task9-build.log`, `task9-playwright.log`,
`task9-npm-audit.json`, `task9-backend-docker.log`,
`task9-frontend-docker-final.log`, `task9-backend-image-recheck.log`, and
`task9-frontend-image-recheck.log`. Scratch logs are ignored; the concise
[verification summary](artifacts/verification/task-9-summary.json) is tracked.

## Browser scope and visual evidence

HTTP exchange routes are fixtures, and the controlled Socket.IO transport binds
only `127.0.0.1:8107`; Next uses a separate `.next-e2e` directory and port 3107.
The tests start no backend lifecycle, guardian, scanner or authenticated client.
Order POSTs in outcome tests terminate in local route fixtures. Screenshot-only
navigation observed no mutating API requests and no page exceptions.

The 59 tests include catalog search/retry/keyboard selection, rapid market
switching, account unavailability/zero, server-owned confirmation and uncertain
intent recovery, Spot/Futures flow isolation, pending/partial/fee displays,
subcent and adjacent price ticks, chart axis bounding boxes, actual reduced-motion
behavior, dialog focus and all five routes at 390/768/1440px. DOM/tape socket tests
exercise the real browser Socket.IO client against the local controlled server.

The labelled [Task 8B captures](artifacts/ui/task-8b) remain the curated visual
set. This run regenerated them and visually inspected the 390px dashboard and
1440px terminal; incidental clock/font timing changes were discarded. Current
[observations](artifacts/verification/task-9-browser-observations.json) preserve
width/overflow readings, page exceptions, console errors and mutation counts.
Some navigation captures deliberately have no Socket.IO fixture server, so their
console includes local `ERR_CONNECTION_REFUSED` messages and the UI correctly
shows disconnected/no-data states. Reduced-motion tests emit the library's
expected reduced-motion notice. No claim of a silent console or live-market
screenshot is made.

## Separate public connectivity checks and limits

The explicit read-only CLI was run for both markets:

```powershell
D:/Projects/VolHelix-AI/env/Scripts/python.exe scripts/test_mcp_connection.py --market spot --symbol BTCUSDT
D:/Projects/VolHelix-AI/env/Scripts/python.exe scripts/test_mcp_connection.py --market futures --symbol BTCUSDT
```

Both exited 1 with `ConnectTimeout`, before receiving server time or price.
Independent `Invoke-WebRequest` calls to production `/api/v3/time` and
`/fapi/v1/time`, each bounded to 12 seconds, also timed out. These are environmental
access failures; no response established an exchange outage, geographic restriction
or a code defect. No TLS validation was disabled and no host was substituted.

A separate disposable `tmp/task9-public-hubs.py` invoked the actual
`MarketDataHub` Spot/Futures connectors with all exchange/LLM credentials blank,
BTCUSDT only, flow persistence off and an isolated temporary flow-store path.
It never imported `backend.main`, entered the app lifespan, or called an order,
account, scan/start endpoint. Each public metadata attempt raised `ConnectTimeout`.
Both hubs were stopped and awaited in `finally`, each retained zero symbols and
the final asyncio pending-task count was zero. Only MainThread and the two
asyncio executor threads were present before `asyncio.run` closed its executor;
no trading thread started. The probe process exited 0 because it records external
failure as evidence, **not** because connectivity passed.

Logs: `tmp/task9-public-spot.log`, `task9-public-futures.log`,
`task9-public-hubs.log`. The earlier Task 6 Futures-only public ingestion proof
(2026-10-22) observed synchronized depth, four trades/tape entries, LIVE health,
one book resync and zero gaps, with awaited cleanup. That dated observation does
not override the current failed access checks. Current public Spot/Futures LIVE
connectivity and a screenshot backed by actual public data remain unverified.

No live/testnet orders, authenticated account queries, Auto-Pilot startup, full
app service smoke or deployment was attempted. Testnet instrument availability,
account settings, real partial fills/fees and guardian execution against an
actual demo account remain unverified. The guardian requires the backend process
to remain running. Historical losses before the first observed equity baseline
are unknown; PnL is gross with actual native fees separate and net PnL unavailable.
No production-readiness or all-bugs-eliminated claim follows from these checks.

## Coverage against the guardrails

| Guardrail in Upgrade_Plan.md section 21 | Evidence / scope |
|---|---|
| 1-2: MIT-compatible original work; same languages/framework | Scoped implementation uses existing Python/Next stack; final whole-branch origin/license review pending |
| 3-4: production public data, testnet execution, no invented fallbacks | Separate market adapters; unavailable-state, no-fill, missing-quote and model-lab regressions; current external access blocked |
| 5-6: nonblocking reads; fixed broadcasts | API thread-pool hooks, synchronous bounded aggregation and fixed-rate Socket.IO regressions |
| 7: preserve risk/confluence | Deterministic entry/exit, funds, finite-value, account mode, leverage and risk regressions in the 329-test suite; 0.70 threshold retained |
| 8: isolate data failures from classic API/guardian | Outage/partial fill/cancel/close/restart/intent recovery coverage; no authenticated live guardian test |
| 9: no wholesale classic-module rewrite | Tasks 1-8B scoped reviews; final whole-branch review is still required |
| 10: bounded buffers/tasks and cleanup | Bounded caches/listeners, disconnect/rotation/lifecycle cleanup regressions and awaited standalone probe shutdown |
| 11: no secrets | No private dotenv or runtime DB copied; final docs/artifacts contain public errors and test summaries only; whole-branch secret/generated-file review pending |
| 12: no completion with failing tests/build | All deterministic gates and image builds pass; external live gate explicitly unresolved; review/integration not marked complete |

## Rulings carried from the execution ledger

The following ledger lines are preserved verbatim, in their original order,
including each stated cost if wrong. The controller must carry them to final
delivery together with any later rulings.

- Ruling: Use managed isolated checkout and existing original Python runtime — authorized implementation permits reversible setup; original user files stay untouched — cost if wrong: environment-dependent tests must be rerun.
- Ruling: Do not repeat unsafe baseline suite until Task 1 isolates clients/stores — inspected lifecycle tests invoke trading routes — cost if wrong: delayed baseline evidence.
- Ruling: Implement persisted first-observed daily/session account-equity baseline for Spot drawdown where Binance lacks direct daily PnL, exposing coverage timestamp and retaining observed loss across deposits — functional risk gating cannot use fabricated0 or remain a permanent stub — cost if wrong: losses before monitoring began are unknown; must clearly disclose coverage and keep missing equity fail-closed.
- Ruling: Bring backward-compatible persisted market fields forward into Task4 submission path — reachable Futures orders must never be stored as default Spot — cost if wrong: Task5 may refine serialization, legacy records remain Spot. Task5 retains lifecycle/guardian/reconciliation ownership.
- Ruling: Split approved Task8 into sequential8A backend/runtime and8B visual/frontend-dependency review units — newly verified financial/runtime findings plus five-route polish exceed one coherent review surface — cost if wrong: one extra review handoff; no added product feature scope. Briefs task-8a-brief.md/task-8b-brief.md, both execute after Task7 review.
- Ruling: Add tracked frontend/vercel.json git.deploymentEnabled.main=false in8B — connectedVercelautoDeploymentwouldotherwiseviolatetheapprovedno-production-deployscopeonmainpush — costifwrong: automaticmainreleasesremaindisableduntiluserexplicitlyre-enables; branchpreviewsunchanged. OfficialVercelgitconfigurationdocsverified; actualprojectrootfrontendconfirmed viaCLI. Task8Bassignedguard, final9mustverifyproductionrefunchanged.
- Ruling: Include narrow sharedprice-gridprecisionfix in8B alongsideUIformatting — actualbackendbucketpriceswerewrong/zero, sofrontformattingalonecannotmeetapprovednew-pair/datahonestyrequirements — costifwrong:Decimalper-tickoverhead; requireO(1),boundedhelpers,targetedflowregressions/volumeconservation/fullbackendverification. No risk/executionchanges. Task8Bimplementerassigned.
