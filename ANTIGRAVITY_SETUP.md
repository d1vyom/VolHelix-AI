# ANTIGRAVITY_SETUP.md — Human-Side Setup for the Order Flow Upgrade

> Companion to `Upgrade_Plan.md`. Everything here is work the **agent cannot do for you**: network checks, `.env` edits, dependency installs, server restarts, MCP configuration, and the manual verification gates between phases.
>
> **Good news first:** this upgrade needs **no new API keys and no paid service.** Binance public market-data websockets are unauthenticated. Your existing testnet keys still cover execution.

---

## 1. Put the plan where the agent will read it

1. Copy both files into the repo root (or `docs/`):
   - `Upgrade_Plan.md`
   - `ANTIGRAVITY_SETUP.md`
2. Commit them before starting, so the agent sees them as tracked context:
   ```
   git add Upgrade_Plan.md ANTIGRAVITY_SETUP.md
   git commit -m "docs: order flow terminal upgrade plan"
   ```
3. Open a new agent session and give it exactly this instruction:

   > Read `Upgrade_Plan.md` in full before writing any code. Execute it phase by phase, starting at Phase 0. Do not skip phases. After each phase, run the acceptance criteria, append to `docs/FLOW_UPGRADE_LOG.md`, and commit. Stop and report if any acceptance criterion cannot be met.

4. Optional but recommended: add a root `AGENTS.md` (the repo already has `frontend/AGENTS.md`) containing one line — *"For the order flow upgrade, `Upgrade_Plan.md` is the specification. Its guardrails section overrides any other instinct."* — so the plan survives context resets.

---

## 2. Network prerequisites (check this before Phase 0)

The agent will stop at Phase 0 if these fail. Test from the same machine that runs the backend:

| Check | Command | Expected |
|---|---|---|
| REST reachable | `curl -s "https://api.binance.com/api/v3/time"` | `{"serverTime":...}` |
| Symbol filters | `curl -s "https://api.binance.com/api/v3/exchangeInfo?symbol=BTCUSDT"` | JSON with `PRICE_FILTER` |
| WebSocket reachable | any WS client against `wss://stream.binance.com:9443/ws/btcusdt@aggTrade` | a stream of trade messages |

**If Binance is blocked on your network** (some campus/ISP networks in India block it, and some regions geo-block `api.binance.com`):
- Try `https://data-api.binance.vision` for public market data (a read-only public mirror of the market endpoints) and tell the agent to make the REST/WS base URLs configurable — the plan already puts `FLOW_WS_BASE_URL` in config.
- Or run the backend on a small cloud VM and point `NEXT_PUBLIC_API_URL` at it.
- Or fall back to the replay mode described in Plan §11.3 for the demo.
- Do **not** route market data through the testnet endpoints. Testnet books are synthetic and would make every footprint meaningless.

**Hackathon venue warning:** test the venue Wi-Fi before you present. Conference networks block websockets more often than you'd expect. Have the replay fixture ready.

---

## 3. `.env` additions

The agent adds these keys to `backend/config.py` and `.env.example`, but **you** must add them to your real `.env` (which is gitignored). Paste this block after Phase 1:

```env
# ── Order Flow Engine ──
FLOW_ENABLED=true
FLOW_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT
FLOW_WS_BASE_URL=wss://stream.binance.com:9443
FLOW_DEPTH_LEVELS=20
FLOW_USE_DIFF_DEPTH=true
FLOW_FOOTPRINT_INTERVALS=1m,5m,15m
FLOW_IMBALANCE_RATIO=3.0
FLOW_STACKED_IMBALANCE_MIN=3
FLOW_WHALE_NOTIONAL_USD=100000
FLOW_BROADCAST_HZ=4
FLOW_CONFLUENCE_ENABLED=false
FLOW_PERSIST_BARS=false
```

Notes:
- Start with **two** symbols (`BTCUSDT,ETHUSDT`) while developing — fewer streams, faster iteration, easier logs. Expand to five at Phase 10.
- Keep `FLOW_CONFLUENCE_ENABLED=false` until Phase 9's shadow-mode run is done. This is the one flag that can change what the bot trades.
- Your existing `BINANCE_API_KEY` / `BINANCE_API_SECRET` / `GOOGLE_API_KEY` entries stay exactly as they are.

---

## 4. Dependencies

**Python** — likely nothing new. `python-binance`, `httpx` and `aiosqlite` are already in `backend/requirements.txt`. If the agent chooses the raw-websocket path in Phase 2, it will add `websockets`. Run after any requirements change:

```
.\env\Scripts\activate
pip install -r backend/requirements.txt
```

**Node** — the plan is deliberately zero-new-dependency; `socket.io-client` is already installed. The only sanctioned exception is `react-resizable-panels` in Phase 8, and only if a hand-rolled grid proves impractical. If the agent adds it:

```
cd frontend
npm install
```

**Review any dependency the agent adds.** If it proposes a charting library for the footprint or heatmap, say no — Plan §7 requires Canvas 2D, and a heavy chart library is exactly how this ends up at 5 fps.

---

## 5. Running the stack during development

Two terminals, both from the repo root:

```
# Terminal 1 — backend
.\env\Scripts\activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

```
# Terminal 2 — frontend
cd frontend
npm run dev
```

Then open `http://localhost:3000/terminal` (exists from Phase 7 onward).

**Important `--reload` caveat:** uvicorn's reloader restarts the process on every file save, which tears down and rebuilds all websocket connections and resyncs every order book. During Phases 2–5, run **without** `--reload` when you want a stable stream to observe, and watch the reconnect logs when you do use it — noisy reconnects there are expected, not a bug.

---

## 6. Manual verification gates

The agent self-tests, but these five checks need human eyes. Do them at the phases listed; don't let the agent tick them for you.

| After | Check | What "pass" looks like |
|---|---|---|
| **Phase 2** | `curl http://localhost:8000/api/flow/status` (or watch backend logs) | Per-symbol `connected: true`, trades arriving, zero gap events after 60 s |
| **Phase 4** | Hit each `/api/flow/*` endpoint in a browser | Real numbers, no `null`s, `server_ts` moving |
| **Phase 7** | Open `/terminal`, watch one 1-minute BTC bar form start to finish | Footprint cells fill, delta updates, POC settles, ladder moves with price, tape scrolls |
| **Phase 7** | **The reconciliation check** — pick a closed 1m bar; compare its `buy_volume` to the sum of buy prints in the tape for that minute; also compare to the kline's `taker buy base volume` | All three agree within rounding. If they don't, the aggressor-side logic is inverted somewhere and **everything downstream is wrong** |
| **Phase 9** | Read the shadow-mode log lines for a full session | You can see what the flow score *would* have changed before you enable it |

Unplug your network for 30 seconds during Phase 7 and plug it back in. The badge should go amber/red and return to green on its own. If you have to refresh the page, the reconnect logic isn't done.

---

## 7. MCP servers & Antigravity configuration

None of these are required — the plan is written to be executable with file editing and a terminal alone. These are the ones that actually earn their place for this specific job:

| MCP / tool | Why it helps here | Priority |
|---|---|---|
| **Filesystem + terminal access** (built in) | The agent must run pytest, npm lint/build and git. Grant repo-scoped write access and terminal execution | **Required** |
| **Browser / Playwright MCP** | Phase 7–8 is UI work. Without it the agent writes canvas rendering code it can never see. With it, it can open `/terminal`, screenshot panels and self-correct layout bugs | **High** — the single biggest quality lever in this upgrade |
| **Context7** (or any live-docs MCP) | Next.js 16 and React 19 post-date most model training data, and `frontend/AGENTS.md` explicitly warns that this Next.js version has breaking changes. Also useful for current Binance API docs | **High** |
| **GitHub MCP** | Branch/PR management at Phase 11; reading issues | Medium |
| **Fetch / HTTP MCP** | Lets the agent verify Binance endpoint shapes directly instead of guessing payload fields | Medium |
| **SQLite MCP** | Only if you enable `FLOW_PERSIST_BARS` in Phase 10 | Low |

Skip anything else. Every extra MCP is extra context the agent burns on tool descriptions instead of your code.

**Agent settings that matter for this job:**
- Give it a **large context window model** — `Upgrade_Plan.md` alone is ~1 000 lines, and `page.tsx` is 1 960.
- Allow **multi-file edits** and **terminal execution without per-command approval**, or an 11-phase plan will take a week of clicking.
- Keep **auto-commit off**. You want to review each phase's diff before it lands.

---

## 8. Cost and time expectations

| Phase group | Rough effort for the agent | Your involvement |
|---|---|---|
| 0–1 (setup, contracts) | Short | `.env` edits, baseline check |
| 2 (websockets + book sync) | **The hardest phase.** Expect iteration | Watch logs, verify resync |
| 3–5 (engines, API, broadcast) | Medium, mostly mechanical | Spot-check endpoints |
| 6–8 (frontend, panels, layout) | **The longest phase.** Canvas rendering needs visual iteration | Frequent — this is where browser MCP pays for itself |
| 9 (strategy integration) | Short but high-risk | Read the shadow logs before enabling |
| 10–11 (hardening, docs) | Medium | Failure-matrix testing, demo rehearsal |

If you're short on time before the hackathon, the minimum viable slice that still demos well is **Phases 0–7 with the footprint chart, DOM ladder and tape only** — skip the heatmap (7.4), volume profile (7.5), the workspace grid (Phase 8, use a fixed layout) and Phase 9. Say so explicitly at the start of the session, or the agent will build all eleven phases.

---

## 9. When something goes wrong

| Symptom | Likely cause | Action |
|---|---|---|
| Footprint buy/sell look inverted vs. the tape | The `m` flag misread. `m=true` means the **seller** was the aggressor | Point the agent at Plan §1.1's aggressor rule and the test in Phase 1 |
| Book desyncs constantly | Diff-depth sync procedure not followed exactly | Plan §2.3, steps 3–5. The `U <= lastUpdateId+1 <= u` condition is the usual miss |
| UI freezes after a few minutes | Per-event React re-renders, or an unbounded buffer | Plan §6.3 (rAF batching) and §10.1 (every deque needs `maxlen`) |
| `429` / `418` from Binance | Depth snapshots too frequent | Plan §10.1 rate-limit handling; raise the resync cooldown |
| Classic dashboard broke | The agent refactored shared code | Guardrail §21.9. Revert that phase's commit and redo it additively |
| Agent starts porting Flowsurface Rust code | Licence violation in progress | Guardrail §21.1. Stop it immediately — GPL-3 code cannot enter this MIT repo |

Keep each phase in its own commit and this is always recoverable with a single `git revert`.

---

*End of ANTIGRAVITY_SETUP.md*
