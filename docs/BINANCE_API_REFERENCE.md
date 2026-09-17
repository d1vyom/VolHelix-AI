# VolHelix AI — Binance REST API Reference

> **Purpose:** Complete reference for every Binance API endpoint the project uses.  
> **Library:** `python-binance` (pip install python-binance)  
> **Docs:** https://python-binance.readthedocs.io/  
> **Official API:** https://binance-docs.github.io/apidocs/spot/en/

---

## Table of Contents

1. [Client Initialization](#1-client-initialization)
2. [Public Market Data (No API Key)](#2-public-market-data)
3. [Account & Balance (Testnet Key Required)](#3-account--balance)
4. [Order Placement (Testnet Key Required)](#4-order-placement)
5. [Order Management](#5-order-management)
6. [Trade History](#6-trade-history)
7. [Exchange Info & Symbol Filters](#7-exchange-info--symbol-filters)
8. [Error Handling](#8-error-handling)
9. [Rate Limits](#9-rate-limits)
10. [Testnet Quirks & Gotchas](#10-testnet-quirks--gotchas)

---

## 1. Client Initialization

```python
from binance.client import Client

# ── Market Data Client (PRODUCTION — real prices, no key needed) ──
market_client = Client("", "")

# ── Trading Client (TESTNET — paper trading, key required) ──
trading_client = Client(
    api_key="your_testnet_api_key",
    api_secret="your_testnet_api_secret",
    testnet=True  # Routes to https://testnet.binance.vision
)
```

**When `testnet=True`:**
- REST API base → `https://testnet.binance.vision`
- WebSocket base → `wss://testnet.binance.vision/ws`

---

## 2. Public Market Data

These endpoints do NOT require authentication. Use the `market_client` (production).

### 2.1 Current Price (Single Symbol)

```python
ticker = market_client.get_symbol_ticker(symbol="BTCUSDT")
# Returns: {"symbol": "BTCUSDT", "price": "67142.50000000"}
price = float(ticker["price"])
```

### 2.2 Current Prices (All Symbols)

```python
tickers = market_client.get_all_tickers()
# Returns: [{"symbol": "BTCUSDT", "price": "67142.50"}, ...]
```

### 2.3 24hr Ticker Statistics

```python
ticker = market_client.get_ticker(symbol="BTCUSDT")
# Returns:
# {
#     "symbol": "BTCUSDT",
#     "priceChange": "1234.50000000",
#     "priceChangePercent": "1.876",
#     "weightedAvgPrice": "66500.12345678",
#     "prevClosePrice": "65908.00000000",
#     "lastPrice": "67142.50000000",
#     "bidPrice": "67142.00000000",
#     "bidQty": "0.50000000",
#     "askPrice": "67143.00000000",
#     "askQty": "0.30000000",
#     "openPrice": "65908.00000000",
#     "highPrice": "68200.00000000",
#     "lowPrice": "65100.00000000",
#     "volume": "45678.12345678",
#     "quoteVolume": "3045678901.12345678",
#     "openTime": 1695916800000,
#     "closeTime": 1696003199999,
#     "count": 1234567
# }
```

### 2.4 Klines (Candlestick/OHLCV)

```python
klines = market_client.get_klines(
    symbol="BTCUSDT",
    interval=Client.KLINE_INTERVAL_1HOUR,  # or "1h"
    limit=100
)
# Each kline is a list:
# [
#     open_time,      # [0]  1695916800000
#     open,           # [1]  "67000.00"
#     high,           # [2]  "67500.00"
#     low,            # [3]  "66800.00"
#     close,          # [4]  "67200.00"
#     volume,         # [5]  "1234.56"
#     close_time,     # [6]  1695920399999
#     quote_volume,   # [7]  "82345678.90"
#     trades_count,   # [8]  54321
#     taker_buy_base, # [9]  "678.90"
#     taker_buy_quote,# [10] "45678901.23"
#     ignore          # [11] "0"
# ]
```

**Available intervals:**
| Constant | String | Description |
|---|---|---|
| `KLINE_INTERVAL_1MINUTE` | `"1m"` | 1 minute |
| `KLINE_INTERVAL_3MINUTE` | `"3m"` | 3 minutes |
| `KLINE_INTERVAL_5MINUTE` | `"5m"` | 5 minutes |
| `KLINE_INTERVAL_15MINUTE` | `"15m"` | 15 minutes |
| `KLINE_INTERVAL_30MINUTE` | `"30m"` | 30 minutes |
| `KLINE_INTERVAL_1HOUR` | `"1h"` | 1 hour |
| `KLINE_INTERVAL_2HOUR` | `"2h"` | 2 hours |
| `KLINE_INTERVAL_4HOUR` | `"4h"` | 4 hours |
| `KLINE_INTERVAL_6HOUR` | `"6h"` | 6 hours |
| `KLINE_INTERVAL_8HOUR` | `"8h"` | 8 hours |
| `KLINE_INTERVAL_12HOUR` | `"12h"` | 12 hours |
| `KLINE_INTERVAL_1DAY` | `"1d"` | 1 day |
| `KLINE_INTERVAL_3DAY` | `"3d"` | 3 days |
| `KLINE_INTERVAL_1WEEK` | `"1w"` | 1 week |
| `KLINE_INTERVAL_1MONTH` | `"1M"` | 1 month |

### 2.5 Order Book (Depth)

```python
depth = market_client.get_order_book(symbol="BTCUSDT", limit=20)
# Returns:
# {
#     "lastUpdateId": 1234567890,
#     "bids": [["67142.00", "0.50"], ["67141.00", "1.20"], ...],
#     "asks": [["67143.00", "0.30"], ["67144.00", "0.80"], ...]
# }
# Each entry is [price, quantity]
```

### 2.6 Recent Trades

```python
trades = market_client.get_recent_trades(symbol="BTCUSDT", limit=50)
# Returns:
# [
#     {
#         "id": 123456789,
#         "price": "67142.50",
#         "qty": "0.015",
#         "quoteQty": "1007.14",
#         "time": 1695916812345,
#         "isBuyerMaker": false,
#         "isBestMatch": true
#     }, ...
# ]
```

### 2.7 Aggregate Trades

```python
agg_trades = market_client.get_aggregate_trades(symbol="BTCUSDT", limit=50)
# Similar to recent trades but aggregated
```

### 2.8 Historical Klines with Start/End Time

```python
from datetime import datetime, timedelta

klines = market_client.get_historical_klines(
    symbol="BTCUSDT",
    interval="1d",
    start_str="1 year ago UTC",
    end_str="now UTC"
)
# Or with timestamps:
klines = market_client.get_historical_klines(
    symbol="BTCUSDT",
    interval="1h",
    start_str=str(int((datetime.now() - timedelta(days=30)).timestamp() * 1000)),
    end_str=str(int(datetime.now().timestamp() * 1000))
)
```

---

## 3. Account & Balance

These require testnet API key. Use `trading_client`.

### 3.1 Get Account Info

```python
account = trading_client.get_account()
# Returns:
# {
#     "makerCommission": 0,
#     "takerCommission": 0,
#     "buyerCommission": 0,
#     "sellerCommission": 0,
#     "canTrade": true,
#     "canWithdraw": false,
#     "canDeposit": false,
#     "updateTime": 1695916800000,
#     "accountType": "SPOT",
#     "balances": [
#         {"asset": "BTC", "free": "1.00000000", "locked": "0.00000000"},
#         {"asset": "USDT", "free": "10000.00000000", "locked": "0.00000000"},
#         ...
#     ]
# }
```

### 3.2 Get Asset Balance

```python
balance = trading_client.get_asset_balance(asset="USDT")
# Returns: {"asset": "USDT", "free": "10000.00", "locked": "0.00"}
```

---

## 4. Order Placement

All orders go to TESTNET. Use `trading_client`.

### 4.1 Market Order (Buy)

```python
# Buy 0.001 BTC at market price
order = trading_client.create_order(
    symbol="BTCUSDT",
    side="BUY",
    type="MARKET",
    quantity=0.001
)

# Or buy $100 worth of BTC (using quoteOrderQty)
order = trading_client.create_order(
    symbol="BTCUSDT",
    side="BUY",
    type="MARKET",
    quoteOrderQty=100.0
)
```

### 4.2 Market Order (Sell)

```python
# Sell 0.001 BTC at market price
order = trading_client.create_order(
    symbol="BTCUSDT",
    side="SELL",
    type="MARKET",
    quantity=0.001
)
```

### 4.3 Limit Order

```python
order = trading_client.create_order(
    symbol="BTCUSDT",
    side="BUY",
    type="LIMIT",
    quantity=0.001,
    price="65000.00",
    timeInForce="GTC"  # Good Till Cancelled
)
```

### 4.4 Order Response

```python
# All create_order calls return:
# {
#     "symbol": "BTCUSDT",
#     "orderId": 12345678,
#     "orderListId": -1,
#     "clientOrderId": "abc123",
#     "transactTime": 1695916812345,
#     "price": "0.00000000",       # 0 for MARKET orders
#     "origQty": "0.00100000",
#     "executedQty": "0.00100000",
#     "cummulativeQuoteQty": "67.14250000",
#     "status": "FILLED",          # or NEW, PARTIALLY_FILLED, CANCELED, etc.
#     "timeInForce": "GTC",
#     "type": "MARKET",
#     "side": "BUY",
#     "fills": [
#         {
#             "price": "67142.50000000",
#             "qty": "0.00100000",
#             "commission": "0.00000100",
#             "commissionAsset": "BTC",
#             "tradeId": 98765432
#         }
#     ]
# }
```

### 4.5 Time-in-Force Options

| Value | Description |
|---|---|
| `GTC` | Good Till Cancelled — stays until filled or cancelled |
| `IOC` | Immediate Or Cancel — fills what it can, cancels the rest |
| `FOK` | Fill Or Kill — must fill entirely or not at all |

---

## 5. Order Management

### 5.1 Get Open Orders

```python
# All open orders
open_orders = trading_client.get_open_orders()

# Open orders for specific symbol
open_orders = trading_client.get_open_orders(symbol="BTCUSDT")
```

### 5.2 Get All Orders (History)

```python
orders = trading_client.get_all_orders(symbol="BTCUSDT", limit=50)
# Returns all orders: open, filled, cancelled, etc.
```

### 5.3 Get Specific Order

```python
order = trading_client.get_order(symbol="BTCUSDT", orderId=12345678)
```

### 5.4 Cancel Order

```python
result = trading_client.cancel_order(symbol="BTCUSDT", orderId=12345678)
```

### 5.5 Cancel All Open Orders for Symbol

```python
# Cancel all open orders for BTCUSDT
result = trading_client.cancel_order(symbol="BTCUSDT")
# Note: This cancels ALL open orders for the symbol
```

---

## 6. Trade History

### 6.1 Get My Trades

```python
trades = trading_client.get_my_trades(symbol="BTCUSDT", limit=50)
# Returns:
# [
#     {
#         "symbol": "BTCUSDT",
#         "id": 98765432,
#         "orderId": 12345678,
#         "price": "67142.50000000",
#         "qty": "0.00100000",
#         "quoteQty": "67.14250000",
#         "commission": "0.00000100",
#         "commissionAsset": "BTC",
#         "time": 1695916812345,
#         "isBuyer": true,
#         "isMaker": false,
#         "isBestMatch": true
#     }, ...
# ]
```

---

## 7. Exchange Info & Symbol Filters

### 7.1 Get Exchange Info

```python
info = market_client.get_exchange_info()
# Returns comprehensive exchange config including all symbols and their trading rules
```

### 7.2 Get Symbol Info (Filters)

```python
info = market_client.get_symbol_info("BTCUSDT")
# Returns:
# {
#     "symbol": "BTCUSDT",
#     "status": "TRADING",
#     "baseAsset": "BTC",
#     "baseAssetPrecision": 8,
#     "quoteAsset": "USDT",
#     "quoteAssetPrecision": 8,
#     "filters": [
#         {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000.00", "tickSize": "0.01"},
#         {"filterType": "LOT_SIZE", "minQty": "0.00001", "maxQty": "9000.00", "stepSize": "0.00001"},
#         {"filterType": "MIN_NOTIONAL", "minNotional": "10.00000000"},
#         {"filterType": "NOTIONAL", "minNotional": "10.00000000", "maxNotional": "9000000.00"},
#         ...
#     ]
# }
```

**Critical filters to respect when placing orders:**

| Filter | What It Means | Example (BTCUSDT) |
|---|---|---|
| `LOT_SIZE.minQty` | Minimum order quantity | 0.00001 BTC |
| `LOT_SIZE.stepSize` | Quantity must be multiple of this | 0.00001 |
| `PRICE_FILTER.tickSize` | Price must be multiple of this | 0.01 |
| `MIN_NOTIONAL.minNotional` | Minimum order value (price × qty) | $10.00 |

### 7.3 Helper: Round Quantity to Valid Step

```python
import math

def round_step_size(quantity: float, step_size: float) -> float:
    """Round quantity to the nearest valid step size."""
    precision = int(round(-math.log10(step_size)))
    return round(quantity - (quantity % step_size), precision)

# Usage:
qty = round_step_size(0.001234, 0.00001)  # → 0.00123
```

---

## 8. Error Handling

```python
from binance.exceptions import BinanceAPIException, BinanceOrderException

try:
    order = trading_client.create_order(...)
except BinanceAPIException as e:
    print(f"API Error: {e.status_code} - {e.message}")
    # Common codes:
    # -1013: Filter failure (LOT_SIZE, MIN_NOTIONAL, etc.)
    # -2010: New order rejected (insufficient balance)
    # -2011: Cancel rejected (unknown order)
    # -2015: Invalid API key
    # -1021: Timestamp out of recvWindow
except BinanceOrderException as e:
    print(f"Order Error: {e.status_code} - {e.message}")
```

**Common error codes:**

| Code | Meaning | Fix |
|---|---|---|
| `-1013` | LOT_SIZE or MIN_NOTIONAL filter failed | Round qty to step_size, ensure notional > minimum |
| `-2010` | Insufficient balance | Check balance before placing order |
| `-2011` | Unknown order (cancel) | Order already filled or cancelled |
| `-2015` | Invalid API key | Regenerate testnet key at testnet.binance.vision |
| `-1021` | Timestamp outside recvWindow | Sync system clock |
| `-1100` | Illegal characters in parameter | Check symbol format (no slashes for spot) |

---

## 9. Rate Limits

Binance rate limits per IP:

| Endpoint Type | Limit |
|---|---|
| **General REST** | 1200 requests/minute |
| **Orders** | 10 orders/second, 100,000 orders/day |
| **WebSocket connections** | 5 per second |
| **WebSocket messages** | 300 per connection |

The `python-binance` library handles rate limit headers automatically. For safety, the BinanceClient uses TTL caching to avoid redundant calls.

---

## 10. Testnet Quirks & Gotchas

| Issue | Details | Workaround |
|---|---|---|
| **Stale market data** | Testnet has fake/old prices | Use production API for market data |
| **Keys expire** | Testnet keys periodically expire | Regenerate from testnet.binance.vision |
| **Limited symbols** | Not all symbols available on testnet | Stick to major pairs: BTCUSDT, ETHUSDT, BNBUSDT |
| **No WebSocket streams** | Testnet WebSocket may be unreliable | Use production WebSocket for market data |
| **Pre-loaded balances** | Testnet comes with test funds | No deposit needed — just use the preloaded balances |
| **Order fills may differ** | Testnet fills may not match production liquidity | Expected behavior for paper trading |
| **No futures on spot testnet** | Spot testnet only supports spot orders | Use `testnet.binancefuture.com` for futures (later) |

---

> **Document Version:** 1.0  
> **Created:** September 17, 2026  
> **Purpose:** Complete Binance API reference for Gemini 3.8 Flash
