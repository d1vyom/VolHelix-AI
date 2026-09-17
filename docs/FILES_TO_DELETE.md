# VolHelix AI — Files to Delete & Code to Remove

> **Purpose:** Explicit list of every file, import, and code block that must be removed to purge Alpaca from the codebase.

---

## 1. Files to DELETE Entirely

| File | Reason |
|---|---|
| `backend/mcp/cli_runner.py` | Alpaca MCP CLI runner — not applicable for Binance |

---

## 2. Dependencies to REMOVE

### File: `backend/requirements.txt`

Remove these two lines:
```
alpaca-py
alpaca-mcp-server
```

### File: `backend/pyproject.toml`

If `alpaca-py` or `alpaca-mcp-server` appear in dependencies, remove them.

---

## 3. Import Statements to REMOVE (by file)

### `backend/mcp/client.py` (FULL REWRITE — all imports go)
```python
# DELETE ALL of these:
from alpaca.trading.client import TradingClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest, 
    StockSnapshotRequest,
    OptionChainRequest,
    OptionSnapshotRequest,
    OptionLatestQuoteRequest
)
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from alpaca.trading.requests import (
    GetOrdersRequest, 
    MarketOrderRequest, 
    LimitOrderRequest,
    ReplaceOrderRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus
from alpaca.common.exceptions import APIError
```

### `backend/engine/auto_trader.py`
```python
# DELETE:
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from alpaca.data.enums import DataFeed
from backend.mcp.client import AlpacaClient
```

### `backend/api/routes.py`
```python
# DELETE (around lines 242-248):
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, CryptoLatestQuoteRequest, StockBarsRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

# Also DELETE (around line 17):
from backend.mcp.client import AlpacaClient
```

### `backend/agents/executor.py`
```python
# Search for and DELETE any:
from backend.mcp.client import AlpacaClient
# and any direct alpaca imports
```

### `backend/agents/market_intel.py`
```python
# Search for and DELETE any:
from backend.mcp.client import AlpacaClient
```

### `backend/agents/orchestrator.py`
```python
# Search for and DELETE any:
from backend.mcp.client import AlpacaClient
```

### `backend/agents/event_scanner.py`
```python
# Search for and DELETE any Alpaca news API imports
```

### `backend/agents/strategy_synthesizer.py`
```python
# Search for and DELETE any:
from backend.mcp.client import AlpacaClient
```

### `backend/store/portfolio_store.py`
```python
# Search for and DELETE any Alpaca references
```

### `backend/utils/market_hours.py`
```python
# Search for and DELETE any Alpaca clock references
```

### `backend/engine/order_flow.py`
```python
# Search for and DELETE any Alpaca data client references
```

---

## 4. Class/Function Definitions to REMOVE or REPLACE

### `backend/mcp/client.py`
- **DELETE** entire `class AlpacaClient` (replace with `class BinanceClient`)

### `backend/api/routes.py`
- **DELETE** function `_get_alpaca_trading_client()`
- **DELETE** function `_get_stock_client()`
- **DELETE** function `_get_crypto_client()`
- **RENAME** all routes from `/api/alpaca/*` to `/api/exchange/*`

### `backend/engine/auto_trader.py`
- **DELETE** method `_get_trading_client()` (replace with `_get_binance_client()`)
- **DELETE** method `_get_stock_client()` (replace with `_get_binance_client()`)

### `backend/config.py`
- **DELETE** `ALPACA_API_KEY` setting
- **DELETE** `ALPACA_API_SECRET` setting
- **DELETE** `ALPACA_BASE_URL` setting

---

## 5. Environment Variable References to REMOVE

### `.env`
```env
# DELETE these lines:
ALPACA_API_KEY=PK6LKRCQQ4V6HP2QUELCYJMZTU
ALPACA_API_SECRET=LN8rieCMsJmWKanGiUy3tjWvjJhxaAWYybY7JQFW2rB
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2
```

### `.env.example`
```env
# DELETE these lines:
ALPACA_API_KEY=your_alpaca_api_key_here
ALPACA_API_SECRET=your_alpaca_api_secret_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

---

## 6. Frontend References to REMOVE

### `frontend/src/lib/api.ts`
- **RENAME** all `Alpaca`-prefixed interfaces and functions (see BINANCE_FRONTEND_MIGRATION.md)
- **CHANGE** all `/api/alpaca/*` URLs to `/api/exchange/*`

### All component files referencing "Alpaca":
- `frontend/src/components/Sidebar.tsx` — Replace text labels
- `frontend/src/components/Header.tsx` — Replace text labels
- `frontend/src/components/CandlestickChart.tsx` — Replace default symbols
- `frontend/src/app/page.tsx` — Replace references
- `frontend/src/app/volatility/page.tsx` — Replace references
- `frontend/src/app/audit/page.tsx` — Replace audit trail tool names
- `frontend/src/app/layout.tsx` — Replace metadata

---

## 7. Documentation References to UPDATE

| File | What to Change |
|---|---|
| `README.md` | Replace all Alpaca references with Binance |
| `PRD.md` | Update architecture diagrams, MCP references, tech stack (this is a major rewrite) |
| `ONE_PAGER.md` | Update submission write-up |
| `INNOVATION.md` | Update if it mentions Alpaca |
| `docker-compose.yml` | Remove any Alpaca MCP server service |

---

## 8. Test Files to UPDATE

| File | What to Change |
|---|---|
| `backend/tests/test_auto_trader.py` | Remove Alpaca mocks, add Binance mocks |
| `backend/tests/test_order_lifecycle.py` | Replace Alpaca order lifecycle with Binance |

---

## 9. Verification Commands

After completing all deletions, run these to confirm zero Alpaca references remain:

```powershell
# Backend (Python files)
Select-String -Path "backend\**\*.py" -Pattern "alpaca" -CaseSensitive:$false -Recurse

# Frontend (TS/TSX files) 
Select-String -Path "frontend\src\**\*.ts","frontend\src\**\*.tsx" -Pattern "alpaca" -CaseSensitive:$false -Recurse

# Config files
Select-String -Path ".env",".env.example","docker-compose.yml" -Pattern "alpaca" -CaseSensitive:$false

# All files
Select-String -Path "**\*" -Pattern "ALPACA" -Recurse -Include "*.py","*.ts","*.tsx","*.env","*.yml","*.md","*.json","*.toml","*.txt"
```

**Expected result:** ZERO matches across the entire codebase (excluding these migration docs themselves).

---

> **Document Version:** 1.0  
> **Created:** September 17, 2026  
> **Purpose:** Deletion checklist for Gemini 3.8 Flash
