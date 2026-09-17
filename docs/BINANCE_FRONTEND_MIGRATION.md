# VolHelix AI — Frontend Migration: Alpaca → Binance

> **Scope:** All TypeScript/React files in `frontend/src/` that reference Alpaca.  
> **Changes:** API endpoint URLs, interface names, component text, symbol selectors.

---

## Table of Contents

1. [API Layer (lib/api.ts)](#1-api-layer)
2. [Types (lib/types.ts)](#2-types)
3. [Components](#3-components)
4. [Pages](#4-pages)
5. [Symbol Selectors & Defaults](#5-symbol-selectors--defaults)

---

## 1. API Layer

### File: `frontend/src/lib/api.ts`

This is the central API client. All `Alpaca`-prefixed names and `/api/alpaca/*` URLs must change.

### Global Rename Map

| Old Name | New Name |
|---|---|
| `AlpacaAccount` | `ExchangeAccount` |
| `AlpacaPosition` | `ExchangePosition` |
| `AlpacaOrder` | `ExchangeOrder` |
| `AlpacaQuote` | `ExchangeQuote` |
| `AlpacaBar` | `ExchangeBar` |
| `AlpacaOrderResponse` | `ExchangeOrderResponse` |
| `AlpacaCloseResponse` | `ExchangeCloseResponse` |
| `getAlpacaAccount()` | `getExchangeAccount()` |
| `getAlpacaPositions()` | `getExchangePositions()` |
| `getAlpacaOrders()` | `getExchangeOrders()` |
| `getAlpacaQuote()` | `getExchangeQuote()` |
| `getAlpacaBars()` | `getExchangeBars()` |
| `submitAlpacaOrder()` | `submitExchangeOrder()` |
| `closeAlpacaPosition()` | `closeExchangePosition()` |
| `cancelAlpacaOrder()` | `cancelExchangeOrder()` |
| `cancelAllAlpacaOrders()` | `cancelAllExchangeOrders()` |

### URL Endpoint Changes

| Old URL | New URL |
|---|---|
| `/api/alpaca/account` | `/api/exchange/account` |
| `/api/alpaca/positions` | `/api/exchange/positions` |
| `/api/alpaca/orders` | `/api/exchange/orders` |
| `/api/alpaca/quote?symbol=...` | `/api/exchange/quote?symbol=...` |
| `/api/alpaca/bars?symbol=...` | `/api/exchange/bars?symbol=...` |
| `/api/alpaca/order` | `/api/exchange/order` |
| `/api/alpaca/close-position` | `/api/exchange/close-position` |
| `/api/alpaca/cancel-all` | `/api/exchange/cancel-all` |
| `/api/alpaca/orders/{id}` (DELETE) | `/api/exchange/orders/{id}` (DELETE) |

### Updated Interface: ExchangeAccount

```typescript
export interface ExchangeAccount {
  equity: number;
  buying_power: number;
  balances: Record<string, { free: number; locked: number; total: number }>;
  status: string;
  can_trade: boolean;
  error?: string;
}
```

### Updated Interface: ExchangeQuote

```typescript
export interface ExchangeQuote {
  symbol: string;
  bid: number;
  ask: number;
  last: number;
  spread: number;
  high: number;
  low: number;
  volume: number;
  change_pct: number;
  timestamp: string;
}
```

### Updated Interface: ExchangeOrder

```typescript
export interface ExchangeOrder {
  order_id: string | number;
  symbol: string;
  side: string;
  type: string;
  status: string;
  price: number;
  orig_qty: number;
  executed_qty: number;
  cummulative_quote_qty: number;
  time_in_force?: string;
  time?: number;
  created_at?: string;
}
```

### Updated Default Fallback Values

Replace stock-based defaults with crypto-based defaults:

```typescript
// OLD:
{ equity: 100000.0, buying_power: 400000.0, cash: 100000.0, ... }

// NEW:
{ equity: 10000.0, buying_power: 10000.0, balances: { USDT: { free: 10000, locked: 0, total: 10000 } }, ... }
```

### Updated Function: getExchangeAccount

```typescript
export async function getExchangeAccount(): Promise<ExchangeAccount> {
  try {
    const res = await fetch(`${API_BASE}/api/exchange/account`);
    return await safeJson<ExchangeAccount>(res, {
      equity: 10000.0,
      buying_power: 10000.0,
      balances: {},
      status: "ACTIVE",
      can_trade: true,
    });
  } catch {
    return {
      equity: 10000.0,
      buying_power: 10000.0,
      balances: {},
      status: "ACTIVE",
      can_trade: true,
    };
  }
}
```

### Updated Function: getExchangeQuote

```typescript
export async function getExchangeQuote(symbol: string): Promise<ExchangeQuote> {
  try {
    const res = await fetch(`${API_BASE}/api/exchange/quote?symbol=${encodeURIComponent(symbol)}`);
    return await safeJson<ExchangeQuote>(res, {
      symbol,
      bid: 0,
      ask: 0,
      last: 0,
      spread: 0,
      high: 0,
      low: 0,
      volume: 0,
      change_pct: 0,
      timestamp: new Date().toISOString(),
    });
  } catch {
    return {
      symbol,
      bid: 0,
      ask: 0,
      last: 0,
      spread: 0,
      high: 0,
      low: 0,
      volume: 0,
      change_pct: 0,
      timestamp: new Date().toISOString(),
    };
  }
}
```

### Updated Function: submitExchangeOrder

```typescript
export async function submitExchangeOrder(
  symbol: string,
  qty: number,
  side: "buy" | "sell",
  order_type: "market" | "limit" = "market",
  limit_price?: number
): Promise<ExchangeOrderResponse> {
  try {
    const res = await fetch(`${API_BASE}/api/exchange/order`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, qty, side, order_type, limit_price }),
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      return { success: false, error: errJson.detail || `Server error: HTTP ${res.status}` };
    }
    return await safeJson<ExchangeOrderResponse>(res, { success: false });
  } catch (e: any) {
    return { success: false, error: e.message || "Failed to submit order" };
  }
}
```

---

## 2. Types

### File: `frontend/src/lib/types.ts` (or `frontend/src/types/`)

Update the MarketSignal type to use crypto-relevant fields:

```typescript
export type WatchedSymbol = "BTCUSDT" | "ETHUSDT" | "SOLUSDT" | "BNBUSDT" | "XRPUSDT";

export const WATCHED_SYMBOLS: WatchedSymbol[] = [
  "BTCUSDT",
  "ETHUSDT",
  "SOLUSDT",
  "BNBUSDT",
  "XRPUSDT",
];

export const SYMBOL_DISPLAY_NAMES: Record<WatchedSymbol, string> = {
  BTCUSDT: "Bitcoin",
  ETHUSDT: "Ethereum",
  SOLUSDT: "Solana",
  BNBUSDT: "BNB",
  XRPUSDT: "XRP",
};
```

Update MarketClockStatus:

```typescript
export interface MarketClockStatus {
  is_open: boolean;    // Always true for crypto
  raw_is_open: boolean;
  simulation_active: boolean;
  simulation_override?: boolean;
  current_time_et: string;
  reason: string;
}
```

---

## 3. Components

### Files to Update

Search for "alpaca" (case-insensitive) in all components and replace:

| File | What to Change |
|---|---|
| `src/components/Sidebar.tsx` | Replace "Alpaca" text labels with "Binance" |
| `src/components/Header.tsx` | Replace "Alpaca" connection status text |
| `src/components/CandlestickChart.tsx` | Update default symbol from stocks to crypto |
| Any component importing from `api.ts` | Update function names per the rename map above |

### Sidebar.tsx Changes

```typescript
// OLD:
"Alpaca Paper Trading"
"Connected to Alpaca"

// NEW:
"Binance Testnet Trading"
"Connected to Binance (Testnet)"
```

### Header.tsx Changes

```typescript
// OLD:
"Alpaca Paper Account"

// NEW:
"Binance Testnet Account"
```

### CandlestickChart.tsx Changes

Replace default symbol:
```typescript
// OLD:
const defaultSymbol = "SPY";

// NEW:
const defaultSymbol = "BTCUSDT";
```

Replace any hardcoded stock symbol references:
```typescript
// OLD:
const symbols = ["SPY", "QQQ", "AAPL", "NVDA", "TSLA"];

// NEW:
const symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];
```

---

## 4. Pages

### File: `frontend/src/app/page.tsx` (Command Center)

- Update default symbol selectors from stocks to crypto pairs
- Replace any "Alpaca" text in UI
- Update the equity curve description (remove SPY benchmark — use BTC benchmark instead)
- Update the symbol dropdown to show crypto pairs

### File: `frontend/src/app/volatility/page.tsx` (Volatility Lab)

- Remove VIX references (not relevant for crypto)
- Replace with crypto volatility metrics (BTC realized vol, ETH/BTC correlation, etc.)
- Update any Alpaca-specific data fetching

### File: `frontend/src/app/audit/page.tsx` (Audit Trail)

- Replace `alpaca_mcp.get_quote` audit references with `binance.get_price`
- Replace `alpaca_mcp.get_account` with `binance.get_account`

### File: `frontend/src/app/layout.tsx`

- Replace any "Alpaca" text in the root layout
- Update metadata/title if it mentions Alpaca

---

## 5. Symbol Selectors & Defaults

### Everywhere a symbol selector or dropdown exists, update the options:

**Old (Stocks):**
```typescript
const SYMBOLS = [
  { value: "SPY", label: "SPY — S&P 500 ETF" },
  { value: "QQQ", label: "QQQ — Nasdaq 100 ETF" },
  { value: "AAPL", label: "AAPL — Apple" },
  { value: "NVDA", label: "NVDA — NVIDIA" },
  { value: "TSLA", label: "TSLA — Tesla" },
];
```

**New (Crypto):**
```typescript
const SYMBOLS = [
  { value: "BTCUSDT", label: "BTC/USDT — Bitcoin" },
  { value: "ETHUSDT", label: "ETH/USDT — Ethereum" },
  { value: "SOLUSDT", label: "SOL/USDT — Solana" },
  { value: "BNBUSDT", label: "BNB/USDT — BNB" },
  { value: "XRPUSDT", label: "XRP/USDT — XRP" },
];
```

### Price Display Format

Crypto prices need different formatting than stock prices:

```typescript
// Stocks: $574.85 (2 decimal places)
// BTC:    $67,142.50 (2 decimal places, with comma separator)
// SOL:    $142.35 (2 decimal places)
// XRP:    $0.5234 (4 decimal places for sub-$1 assets)

function formatCryptoPrice(price: number): string {
  if (price >= 1000) {
    return `$${price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  } else if (price >= 1) {
    return `$${price.toFixed(2)}`;
  } else {
    return `$${price.toFixed(4)}`;
  }
}
```

### Quantity Input

Crypto allows fractional quantities (e.g., 0.001 BTC). Ensure quantity inputs support decimal values:

```typescript
// OLD: integer qty for stocks
<input type="number" min="1" step="1" />

// NEW: fractional qty for crypto
<input type="number" min="0.00001" step="0.001" />
```

---

## Complete Grep Verification

After migration, run these commands to verify no Alpaca references remain:

```bash
# In PowerShell from project root:
Select-String -Path "frontend\src\**\*.ts","frontend\src\**\*.tsx" -Pattern "alpaca" -CaseSensitive:$false -Recurse

# Should return ZERO results (or only migration comments)
```

---

> **Document Version:** 1.0  
> **Created:** September 17, 2026  
> **Purpose:** Frontend migration guide for Gemini 3.8 Flash
