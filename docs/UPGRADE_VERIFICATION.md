# Upgrade verification - Task 8B

Date: 2026-10-23. Base dfea572. Approved design and Upgrade_Plan section 21 govern this change.

## Reproduced repairs

- Dashboard displayed gross realized PnL as net. Native fee maps/coverage/dust now remain visible with fee-exclusive labels and unavailable net results. Nullable portfolio and position fields match the backend contract.
- Subcent values rounded to zero in summary, book and chart labels. Formatters preserve nonzero values, chart axes reserve label space, and hypothetical volatility strikes scale with tiny source quotes.
- Controller independently reproduced `round_to_tick(0.3, 0.1) == 0.2` and `round_to_tick(3e-9, 1e-9) == 0`. Shared decimal grid arithmetic now preserves exact boundaries, floors bids/trades, ceils asks and multiplies tick groups without binary product drift. Footprint/profile/heatmap/book reuse the same helper. Per-tick work stays constant; no new buffers/tasks, fees, execution rules or risk logic are introduced.
- Audit HTTP failure appeared as an empty successful trail. Loading/unavailable/retry now remain distinct; fetch lifecycle owns its abort controller and initial timer.
- Unknown flow rates/absorption appeared as zeros/NONE. Missing metrics are dashes; observed zero slope/ratio remains zero. Unsupported profile mode affordances and unused pseudo-historical VWAP fields were removed.
- Modal keyboard focus escaped; preview confirmation now cycles keyboard focus and returns to preview on close.

## Dependency evidence

Current registry verified Next 16.4.3 and matching eslint-config-next. Official release: https://github.com/vercel/next.js/releases/tag/v16.4.3 . Official affected/fixed range: https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw . Matching framework packages plus compatible sharp 0.35.5, brace-expansion and source-map-js lockfile patches resolve the observed npm audit report. No force downgrade or new direct dependency. Updated bundled Next font/CSS/upgrade guides and managed frontend AGENTS instructions read.

## Verification evidence

- Backend RED: `D:/Projects/VolHelix-AI/env/Scripts/python.exe -m pytest -q backend/tests/test_price_grid.py`: 9 failed, 2 passed. Exact boundary/tiny/aggregated volume/bid-floor/ask-ceil cases reproduced.
- Backend GREEN: same command plus `test_footprint.py test_volume_profile.py test_heatmap.py test_orderbook_sync.py`: 16 passed, 2 existing SDK deprecation warnings, 4.19s.
- Full bare-root backend: `D:/Projects/VolHelix-AI/env/Scripts/python.exe -m pytest -q`: 329 passed, 2 existing SDK warnings, 46.65s. Network-denial fixture and temporary databases active.
- Frontend behavioral RED: gross/net, null PnL, tiny quotes, unavailable metrics, modal focus, audit failure, theoretical tiny-strike source quote, and unknown win-rate tests failed at the intended missing behavior. Earlier integration runs exposed an old dash-only assertion and a test-fixture variable typo; both corrected and final gates rerun.
- Final frontend gates are recorded in the task report after completion.
- [Screenshots and visual walkthrough](artifacts/ui/task-8b/README.md): five routes at 390/768/1440 plus native-fee/modal/subcent-DOM fixtures, computed-font and width observations, console details.

## Release boundary

`frontend/vercel.json` disables automatic Git deployments for main, preserving the approved no-production-deployment scope. Unspecified preview branches retain their existing behavior. Removing this guard requires explicit release approval. No remote setting, deployment or push was performed by Task 8B.

All trading/account checks are deterministic fixtures; no live order, guardian/scanner startup, keys or production readiness claim. Task 9 owns public read-only proof and final current Docker images.

Final frontend gates: 43 browser tests passed (1.1m), lint passed with zero warnings/errors, standalone TypeScript passed, production build passed on Next 16.4.3. Subsequent screenshot/fixture consistency checks: 6 capture/behavior tests passed, then 3 socket/fee tests passed with lint and build green. All saved PNGs were opened for visual inspection. npm audit: 0 vulnerabilities. React checklist and exact local log paths are retained in the Task 8B scratch report.

Final Liquidity preset check passed (1 browser test, 6.9s) after stacking its right-hand panels; production build passed. The additional desktop preset capture brings the inspected set to 19 PNGs.

## Task 8B review round 1 - 2026-10-24

I1: unit prices now use one separate Intl price formatter with 17 significant digits at every magnitude; the current instrument contract supplies no tick metadata, so this preserves representable values without inventing tick rules. Currency totals retain formatMoney. Header, classic book/stats/positions/orders/ledger, candlestick OHLC/axes, volatility source/TP/SL and flow DOM/tape/chart/profile consumers share the price formatter.

I2: /history entry uses the safe price formatter and explicit null checks. Actual zero remains zero; missing entry remains unavailable. A legacy proposal net premium is labelled separately and is never silently presented as the executed entry.

M1: the client app layout now wraps all motion components in MotionConfig reducedMotion="user". The installed library's positional-key handling includes width, so no duplicate per-component preference hook is needed. Earlier reduced-motion screenshots established rendering only; they did not prove Framer Motion behavior. New requestAnimationFrame tests sample actual sidebar widths and history translations with browser animations enabled: reduced motion yields 40 width frames + 40 history frames with zero intermediate values; the no-preference control records 12 intermediate widths and 35 intermediate translations. This is behavioral evidence, not a screenshot inference.

Verification: focused initial RED 7 failed plus two DOM display/staging RED failures. After repair, `npx playwright test tests/review-fixes.spec.ts tests/flow-transport.spec.ts` passed 12 tests (20.5s). Five existing adjacent accounting/selection/confirmation regressions passed (10.9s). `npm run lint` passed without warnings, standalone `npx tsc --noEmit` passed, and `npm run build` passed. No backend/dependency changes or full-suite rerun in this frontend-only repair; Task 9 owns final full-suite and current Docker checks. All trading data are offline fixtures; no live orders, autonomous runtime startup, credentials, push or deployment.
