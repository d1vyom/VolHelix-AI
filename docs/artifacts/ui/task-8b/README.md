# Task 8B interface evidence

Captured 2026-10-23 using Chromium/Playwright, offline account/read fixtures and an isolated `.next-e2e` cache. Every image is explicitly labelled **OFFLINE UI FIXTURE**. These images establish frontend behavior and layout only. They are not evidence of live market data, authenticated execution, or production readiness. No live orders or trading services were started.

## Five route walkthrough

| Step | Surface and health | 390 px | 768 px | 1440 px |
|---|---|---|---|---|
| 1 | Dashboard: account zero preserved; compact summary; order ticket reachable before the empty positions dock on mobile. Dense ledger tabs scroll within their panel. | [Mobile](dashboard-390.png) | [Tablet](dashboard-768.png) | [Desktop](dashboard-1440.png) |
| 2 | Pro terminal: adjacent desktop ticket, stacked readable mobile panels, unknown flow metrics shown as dashes, disconnected feed explicit. | [Mobile](terminal-390.png) | [Tablet](terminal-768.png) | [Desktop](terminal-1440.png) |
| 3 | Volatility: model visibly illustrative; source quote required; observed IV/Greeks/regime unavailable. The rendered chart is a hypothetical surface, not empirical observations. | [Mobile](volatility-390.png) | [Tablet](volatility-768.png) | [Desktop](volatility-1440.png) |
| 4 | Audit: search fits; empty success distinct from unavailable/retry. Empty screenshot contains no claimed risk verdict. | [Mobile](audit-390.png) | [Tablet](audit-768.png) | [Desktop](audit-1440.png) |
| 5 | History: gross/fee-exclusive accounting, unavailable ratios without samples, native fees and coverage; horizontally scrollable dense ledger. | [Mobile](history-390.png) | [Tablet](history-768.png) | [Desktop](history-1440.png) |

## Behavioral states

- [Gross gain with larger native fees and retained dust](history-native-fees-1440.png): +0.01 gross is explicitly fee-exclusive; 0.02 BNB / 0.03 USDT remain in their actual assets; net remains unavailable.
- [Mobile confirmation](confirmation-390.png): focus cycles inside the modal, Escape returns to preview, and dismissing sends no order.
- [Exact subcent DOM staging](terminal-subcent-dom-390.png): a real local Socket.IO fixture supplies the nonzero row; clicking stages 0.00000123 without dispatching an order. The stream is deliberately marked stale.

## Visual and accessibility findings

The fresh baseline used system body fallback and serif-looking mono labels. Final computed body font is Geist on every route. Theme font variables now resolve at the element. Charcoal/amber tokens and the original logo are preserved. The broad tablet sidebar no longer squeezes content, and collapsed navigation retains accessible names. Desktop DOM/tape panels have readable columns; mobile Pro panels are full width. Profile mode labels with no behavior were removed. Current VWAP is not invented as historical chart data.

Observed document widths equal 390 / 768 / 1440 in the corresponding captures. Dense information remains in locally scrollable panels. Browser page errors are empty. Capture console logs contain only the expected local socket connection refusal in disconnected fixture states; it is displayed honestly in the UI. No API POST requests occur during the 15 route captures. Observations and console details are preserved in `observations-*.json`.

Keyboard search, mobile navigation, confirmation focus/Escape, reduced-motion rendering, zero/unknown balances, stale positions/ledger, failed scan states, and stable execution intents are covered by the browser suite. Screenshots do not establish complete WCAG compliance or authenticated trading readiness. Read-only public data proof and final Docker images are Task 9 gates.

Additional [Liquidity preset inspection](terminal-liquidity-1280.png) keeps its DOM/tape/profile in a readable stacked right column on desktop; the existing Analysis preset exposes only the supported session profile.
