# Market-aware orderflow transport

Verified 2026-10-22. Public market data only; trading and risk paths are unchanged.


- Market literals are `spot` and `futures`. Every `/api/flow/*` GET takes `market=spot` default. POST `/api/flow/subscribe` and `/unsubscribe` body is `{symbol:"ETHUSDT", market:"futures"}` (market optional defaults Spot). Subscribe awaits metadata/state/network task setup; it does not assert market data is LIVE. Failed input422; cap429; exchange/setup unavailable503. Unknown/unsubscribed snapshot returns200 `{success:false,subscribed:false,error:"Symbol not subscribed",market}`.
- All successful snapshots include top-level `market` and `symbol`, except status has `market`, `symbols`, `health`. Health records include market and symbol. Snapshot panel paths unchanged: footprint/dom/tape/heatmap/volume-profile/cvd/metrics/symbol-info. Cache is separately bounded64entries, with market+hub state generation in keys.
- Socket event names remain `flow_subscribe`, `flow_unsubscribe` with `{market,symbol}`. Room is `flow:<market>:<SYMBOL>`, e.g. `flow:futures:BTCUSDT`; unsubscribe and disconnect release per-SID ownership once. Repeated subscribe same SID/market/symbol is idempotent. Ack `{success:true,market,symbol,room,status}`; failure ack/event `flow:error` is `{success:false,error}`. Browser `connect` emits generic statusWAITING, not LIVE.
- Data event names `flow:tape`, `flow:dom`, `flow:footprint`, `flow:heatmap`, `flow:metrics`, `flow:health` unchanged. Each payload includes top-level market/symbol. DOM uses serialized DomAnalytics, footprint `{interval,bar,is_closed}`, heatmap is the latest HeatmapFrame `{ts_bin,levels}`, tape `{entries:[TapeEntry...]}` max200 per batch; metrics FlowMetrics including health; health StreamHealth. Slow broadcast default4Hz, tape10Hz.
- LIVE requires real fresh trade+book timestamps and synchronized depth. WAITING means incomplete warmup or awaiting synchronization; STALE means either stream older than configurable FLOW_STALE_AFTER_MS(default15000); gap/error can be DEGRADED; initial no data DISCONNECTED; disabled snapshots503/statusenabledfalse. Task7 should check health.status, never infer LIVE from socket handshake. Reject/ignore frames for a stale selection.
- Subscribe socket before REST hydration (wait for successful ack); no REST subscribe is necessary for a socket-owned panel. If an explicit REST subscription is used, balance its separate REST unsubscribe. Demand cap FLOW_MAX_ACTIVE_SYMBOLS(default10) counts non-pinned market/symbol pairs across both markets; duplicate listeners share one stream. Configured startup Spot symbols remain pinned and exempt; Futures lazy/no pinned streams.
- REST bounds: footprintlimit1..240, tape1..2000, CVD1..240, DOMlevels1..100, heatmapwindow1..600, positive finite tick_group. Footprint bars include populated forming cells and their actual tick_group; exceptional ranges coarsen real cells to at most512 display rows without changing OHLC or volumes. Use each bar's grouping. New symbols derive default grouping from the first genuine trade price (metadata tick until then).
- Public Futures REST fapi.binance.com/fapi/v1 and sockets depth/public, aggTrade/market; no auth/trading. Spot paths remain defaults. No change to classic order routes, auto-trader, guardian or risk gate.

## Frontend connection

The shared header selection scopes dashboard reads, order tickets and terminal
subscriptions to `market` plus `symbol`. Every new intent receives a stable client
ID; an uncertain response is retained in tab session storage and reconciled with
the original payload, including after reload or a market switch. Spot sells use
the tracked position close action with its qualified trade ID.

REST defaults to relative `/api` through Next's `BACKEND_URL` rewrite. Socket.IO
uses an explicit browser URL because the Next rewrite does not provide a reliable
WebSocket upgrade. At build time its precedence is `NEXT_PUBLIC_SOCKET_URL`,
`NEXT_PUBLIC_API_URL`, `BACKEND_URL`, then `http://127.0.0.1:8000`. These values are
public endpoints, never credentials. When a Docker/service hostname is used for
`BACKEND_URL`, configure `NEXT_PUBLIC_SOCKET_URL` to a URL reachable by the browser;
restart/rebuild after changing public values. The local default needs no env file.
The socket waits for `flow_subscribe` ACK before hydrating. Bounded REST refresh
every five seconds includes volume profile; unsubscribe/disconnect and aborted
requests release the previous selection. Socket connection alone never means LIVE.

Offline browser verification: in `frontend/`, run `npx playwright test`. Its Next
cache uses `.next-e2e`; controlled Socket.IO listens only on `127.0.0.1:8107`. HTTP
exchange endpoints are fixtures; no backend app, guardian or live orders start.

Execution failures use `detail: {outcome, message, market, client_order_id}`.
`REJECTED` means a persisted exchange rejection, `NOT_DISPATCHED` means a
pre-dispatch check prevented execution, and `UNKNOWN` retains the original intent
and reservation. HTTP502 alone never determines the outcome. Successful actual
acknowledgements include `outcome: "ACKNOWLEDGED"`.

`POST /api/market/order-intents/{client_order_id}/reconcile?market=spot|futures`
takes no order body. It loads the original durable payload and only queries the
exchange or reuses its terminal acknowledgement; it cannot create another order.
An actual acknowledgement updates the entry ledger or the original tracked exit.
Intent-only pending rows use this endpoint without session storage. Their Cancel
action stays disabled until reconciliation establishes a recorded trade identity.

## Binance references

- [Futures routed connections](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect): separate depth/public and aggTrade/market routes.
- [Futures book synchronization](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly): inclusive snapshot bridge and subsequent pu chain. Spot's snapshot-plus-one bridge and sequence rule stay separate.

The deterministic market/lifecycle fixtures live in `backend/tests/test_flow_markets.py`. A separate read-only BTCUSDT Futures stream smoke observed trades, synchronized depth and LIVE health, and awaited clean shutdown without importing the main app or starting the guardian.
