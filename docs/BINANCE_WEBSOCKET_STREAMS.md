# VolHelix AI — Binance WebSocket Streams Reference

> **Purpose:** Real-time market data and order update streams via WebSocket.  
> **Library:** `python-binance` has built-in WebSocket support via `BinanceSocketManager`.  
> **Use production WebSocket for market data, testnet WebSocket for user data (order fills).**

---

## Table of Contents

1. [WebSocket Architecture](#1-websocket-architecture)
2. [Market Data Streams (Production)](#2-market-data-streams)
3. [User Data Stream (Testnet)](#3-user-data-stream)
4. [Integration with Dashboard WebSocket](#4-integration-with-dashboard-websocket)
5. [Connection Management](#5-connection-management)

---

## 1. WebSocket Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    WEBSOCKET STREAMS                         │
│                                                              │
│  ┌───────────────────────────┐  ┌──────────────────────────┐│
│  │  PRODUCTION WS            │  │  TESTNET WS              ││
│  │  wss://stream.binance.com │  │  wss://testnet.binance.  ││
│  │      :9443/ws             │  │      vision/ws           ││
│  │                           │  │                          ││
│  │  • Price tickers          │  │  • Order fills           ││
│  │  • Kline updates          │  │  • Balance changes       ││
│  │  • Depth updates          │  │  • Account updates       ││
│  │  • Trade streams          │  │                          ││
│  │  • Mini tickers           │  │                          ││
│  └───────────────────────────┘  └──────────────────────────┘│
│              │                              │                │
│              ▼                              ▼                │
│  ┌──────────────────────────────────────────────────────────┐│
│  │              VolHelix Backend (Python)                    ││
│  │              Processes + forwards to Dashboard            ││
│  └──────────────────────────────────────────────────────────┘│
│              │                                               │
│              ▼                                               │
│  ┌──────────────────────────────────────────────────────────┐│
│  │              Socket.IO → Next.js Dashboard                ││
│  └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Market Data Streams

### 2.1 Setup with BinanceSocketManager

```python
import asyncio
from binance import AsyncClient, BinanceSocketManager

async def start_market_streams():
    # Use production client for real data (no API key for public streams)
    client = await AsyncClient.create()
    bm = BinanceSocketManager(client)

    # Start streams...
    
    # When done:
    await client.close_connection()
```

### 2.2 Individual Symbol Ticker (Real-time price)

```python
async def price_stream(symbol: str = "BTCUSDT"):
    client = await AsyncClient.create()
    bm = BinanceSocketManager(client)
    
    # Mini ticker — lightweight, just price and volume
    ts = bm.symbol_miniticker_socket(symbol)
    
    async with ts as stream:
        while True:
            msg = await stream.recv()
            # msg = {
            #     "e": "24hrMiniTicker",
            #     "E": 1695916812345,   # Event time
            #     "s": "BTCUSDT",       # Symbol
            #     "c": "67142.50",      # Close price (current price)
            #     "o": "65908.00",      # Open price
            #     "h": "68200.00",      # High
            #     "l": "65100.00",      # Low
            #     "v": "45678.12",      # Total traded base volume
            #     "q": "3045678901.12"  # Total traded quote volume
            # }
            price = float(msg["c"])
            print(f"{symbol}: ${price:,.2f}")
```

### 2.3 All Market Mini Tickers (All symbols at once)

```python
async def all_tickers_stream():
    client = await AsyncClient.create()
    bm = BinanceSocketManager(client)
    
    ts = bm.all_miniticker_socket()
    
    async with ts as stream:
        while True:
            msgs = await stream.recv()
            # msgs is a list of mini tickers for ALL symbols
            for msg in msgs:
                symbol = msg["s"]
                price = float(msg["c"])
                # Filter for watched symbols only
                if symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]:
                    print(f"{symbol}: ${price:,.2f}")
```

### 2.4 Kline (Candlestick) Stream

```python
async def kline_stream(symbol: str = "BTCUSDT", interval: str = "1m"):
    client = await AsyncClient.create()
    bm = BinanceSocketManager(client)
    
    ts = bm.kline_socket(symbol, interval=interval)
    
    async with ts as stream:
        while True:
            msg = await stream.recv()
            kline = msg["k"]
            # kline = {
            #     "t": 1695916800000,    # Kline start time
            #     "T": 1695916859999,    # Kline close time
            #     "s": "BTCUSDT",        # Symbol
            #     "i": "1m",             # Interval
            #     "o": "67100.00",       # Open
            #     "c": "67142.50",       # Close
            #     "h": "67150.00",       # High
            #     "l": "67090.00",       # Low
            #     "v": "12.345",         # Volume
            #     "n": 456,              # Number of trades
            #     "x": false,            # Is this kline closed?
            #     "q": "828123.45",      # Quote volume
            # }
            if kline["x"]:  # Only process closed candles
                print(f"Closed candle: O={kline['o']} H={kline['h']} L={kline['l']} C={kline['c']}")
```

### 2.5 Depth (Order Book) Stream

```python
async def depth_stream(symbol: str = "BTCUSDT"):
    client = await AsyncClient.create()
    bm = BinanceSocketManager(client)
    
    ts = bm.depth_socket(symbol, depth=BinanceSocketManager.WEBSOCKET_DEPTH_20)
    
    async with ts as stream:
        while True:
            msg = await stream.recv()
            # msg = {
            #     "lastUpdateId": 1234567890,
            #     "bids": [["67142.00", "0.50"], ...],  # top 20 bids
            #     "asks": [["67143.00", "0.30"], ...]   # top 20 asks
            # }
            best_bid = float(msg["bids"][0][0])
            best_ask = float(msg["asks"][0][0])
            spread = best_ask - best_bid
            print(f"Bid: {best_bid} | Ask: {best_ask} | Spread: {spread:.2f}")
```

### 2.6 Trade Stream (Individual trades)

```python
async def trade_stream(symbol: str = "BTCUSDT"):
    client = await AsyncClient.create()
    bm = BinanceSocketManager(client)
    
    ts = bm.trade_socket(symbol)
    
    async with ts as stream:
        while True:
            msg = await stream.recv()
            # msg = {
            #     "e": "trade",
            #     "E": 1695916812345,
            #     "s": "BTCUSDT",
            #     "t": 123456789,        # Trade ID
            #     "p": "67142.50",       # Price
            #     "q": "0.015",          # Quantity
            #     "T": 1695916812345,    # Trade time
            #     "m": false,            # Is buyer the maker?
            # }
            price = float(msg["p"])
            qty = float(msg["q"])
            side = "SELL" if msg["m"] else "BUY"
            print(f"{side} {qty} BTC @ ${price:,.2f}")
```

### 2.7 Multi-Symbol Streams (Multiplexed)

```python
async def multi_symbol_stream():
    client = await AsyncClient.create()
    bm = BinanceSocketManager(client)
    
    # Subscribe to multiple streams at once
    ts = bm.multiplex_socket([
        "btcusdt@miniTicker",
        "ethusdt@miniTicker",
        "solusdt@miniTicker",
        "bnbusdt@miniTicker",
        "xrpusdt@miniTicker",
    ])
    
    async with ts as stream:
        while True:
            msg = await stream.recv()
            data = msg["data"]
            symbol = data["s"]
            price = float(data["c"])
            print(f"{symbol}: ${price:,.2f}")
```

---

## 3. User Data Stream

User data streams deliver **order updates** and **balance changes** in real-time. Use TESTNET client.

### 3.1 Setup User Data Stream

```python
async def user_data_stream():
    # Use testnet client for user data
    client = await AsyncClient.create(
        api_key="your_testnet_key",
        api_secret="your_testnet_secret",
        testnet=True
    )
    bm = BinanceSocketManager(client)
    
    ts = bm.user_socket()
    
    async with ts as stream:
        while True:
            msg = await stream.recv()
            event_type = msg.get("e")
            
            if event_type == "executionReport":
                # Order update
                handle_order_update(msg)
            elif event_type == "outboundAccountPosition":
                # Balance change
                handle_balance_update(msg)

def handle_order_update(msg):
    """Process order fill/update events."""
    # msg = {
    #     "e": "executionReport",
    #     "s": "BTCUSDT",           # Symbol
    #     "S": "BUY",               # Side
    #     "o": "MARKET",            # Order type
    #     "q": "0.001",             # Quantity
    #     "p": "0.00",              # Price (0 for MARKET)
    #     "X": "FILLED",            # Current order status
    #     "i": 12345678,            # Order ID
    #     "l": "0.001",             # Last executed quantity
    #     "L": "67142.50",          # Last executed price
    #     "z": "0.001",             # Cumulative filled quantity
    #     "Z": "67.14",             # Cumulative quote qty
    #     "n": "0.000001",          # Commission amount
    #     "N": "BTC",               # Commission asset
    #     "T": 1695916812345,       # Transaction time
    # }
    status = msg["X"]
    symbol = msg["s"]
    side = msg["S"]
    
    if status == "FILLED":
        fill_price = float(msg["L"])
        qty = float(msg["l"])
        print(f"ORDER FILLED: {side} {qty} {symbol} @ ${fill_price:,.2f}")
    elif status == "NEW":
        print(f"ORDER PLACED: {side} {msg['q']} {symbol}")
    elif status == "CANCELED":
        print(f"ORDER CANCELLED: {symbol}")

def handle_balance_update(msg):
    """Process balance change events."""
    # msg = {
    #     "e": "outboundAccountPosition",
    #     "E": 1695916812345,
    #     "u": 1695916812345,
    #     "B": [
    #         {"a": "USDT", "f": "9932.86", "l": "0.00"},
    #         {"a": "BTC", "f": "1.001", "l": "0.00"}
    #     ]
    # }
    for balance in msg["B"]:
        asset = balance["a"]
        free = float(balance["f"])
        locked = float(balance["l"])
        print(f"Balance update: {asset} = {free} free, {locked} locked")
```

---

## 4. Integration with Dashboard WebSocket

### How to bridge Binance WS → Dashboard Socket.IO

```python
import asyncio
import socketio
from binance import AsyncClient, BinanceSocketManager

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

async def start_binance_ws_bridge():
    """Bridge Binance WebSocket data to the frontend via Socket.IO."""
    client = await AsyncClient.create()
    bm = BinanceSocketManager(client)
    
    # Stream mini tickers for watched symbols
    ts = bm.multiplex_socket([
        "btcusdt@miniTicker",
        "ethusdt@miniTicker",
        "solusdt@miniTicker",
        "bnbusdt@miniTicker",
        "xrpusdt@miniTicker",
    ])
    
    async with ts as stream:
        while True:
            msg = await stream.recv()
            data = msg["data"]
            
            # Forward to dashboard via Socket.IO
            await sio.emit("price_update", {
                "symbol": data["s"],
                "price": float(data["c"]),
                "high": float(data["h"]),
                "low": float(data["l"]),
                "volume": float(data["v"]),
                "timestamp": data["E"],
            })
```

### Frontend Socket.IO Consumer

```typescript
// In useWebSocket.ts hook
socket.on("price_update", (data: {
  symbol: string;
  price: number;
  high: number;
  low: number;
  volume: number;
  timestamp: number;
}) => {
  // Update price state for the symbol
  setPrices(prev => ({
    ...prev,
    [data.symbol]: data.price
  }));
});
```

---

## 5. Connection Management

### 5.1 Reconnection Strategy

```python
import asyncio
from binance import AsyncClient, BinanceSocketManager

class BinanceWSManager:
    """Manages WebSocket connections with auto-reconnect."""
    
    def __init__(self):
        self.client = None
        self.bm = None
        self.running = False
        self.reconnect_delay = 5  # seconds
    
    async def start(self):
        self.running = True
        while self.running:
            try:
                self.client = await AsyncClient.create()
                self.bm = BinanceSocketManager(self.client)
                await self._run_streams()
            except Exception as e:
                print(f"WebSocket error: {e}. Reconnecting in {self.reconnect_delay}s...")
                await asyncio.sleep(self.reconnect_delay)
            finally:
                if self.client:
                    await self.client.close_connection()
    
    async def _run_streams(self):
        ts = self.bm.multiplex_socket([
            "btcusdt@miniTicker",
            "ethusdt@miniTicker",
        ])
        async with ts as stream:
            while self.running:
                msg = await stream.recv()
                await self._process_message(msg)
    
    async def _process_message(self, msg):
        # Process and forward to dashboard
        pass
    
    def stop(self):
        self.running = False
```

### 5.2 Available Stream Names (for multiplex_socket)

| Stream Name | Description |
|---|---|
| `btcusdt@miniTicker` | Mini ticker (price, volume) |
| `btcusdt@ticker` | Full 24hr ticker |
| `btcusdt@kline_1m` | 1-minute klines |
| `btcusdt@kline_1h` | 1-hour klines |
| `btcusdt@depth20@100ms` | Order book top 20, 100ms updates |
| `btcusdt@trade` | Individual trades |
| `btcusdt@aggTrade` | Aggregated trades |
| `btcusdt@bookTicker` | Best bid/ask (fastest) |

---

> **Document Version:** 1.0  
> **Created:** September 17, 2026  
> **Purpose:** WebSocket reference for Gemini 3.8 Flash

---

## 6. Order Flow Engine Specifics (Phase 11 Addition)

### 6.1 `aggTrade` Payload Specification
The `aggTrade` stream provides grouped trades. This is the foundation of footprint and delta calculations.
```json
{
  "e": "aggTrade",
  "E": 1695916812345,
  "s": "BTCUSDT",
  "a": 12345,         // Aggregate trade ID (monotonic, use for gap detection)
  "p": "67142.50",    // Price
  "q": "0.015",       // Quantity
  "f": 100,           // First underlying trade ID
  "l": 105,           // Last underlying trade ID
  "T": 1695916812300, // Trade time (Use this for bucketing)
  "m": true           // Is buyer the market maker? If true, aggressor was SELLER.
}
```

### 6.2 Diff-Depth Sync Procedure
1. Open a stream to `wss://stream.binance.com:9443/ws/<symbol>@depth@100ms`.
2. Buffer the events you receive from the stream.
3. Get a depth snapshot from `https://api.binance.com/api/v3/depth?symbol=<symbol>&limit=1000`.
4. Drop any event where `u` (final update ID) is `<= lastUpdateId` in the snapshot.
5. The first processed event should have `U <= lastUpdateId+1` AND `u >= lastUpdateId+1`.
6. While applying updates, each new event's `U` should be equal to the previous event's `u+1`. If not, a gap occurred and you must resync.

### 6.3 Connection Limits and Rotation
- **Stream Limit**: Maximum ~1024 streams per connection (chunk at 200).
- **Control Message Limit**: 5 inbound control messages (SUBSCRIBE/UNSUBSCRIBE) per second.
- **24-Hour Rotation**: Binance forcefully closes websocket connections after 24 hours. The stream manager must proactively reconnect/rotate at the 23-hour mark.
- **Pings/Pongs**: Handled automatically by the underlying library, but dropping them leads to disconnects.
