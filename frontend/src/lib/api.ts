import type { Market } from "./market";
import { PortfolioSnapshot, TradeRecord, MarketSignal, MarketClockStatus, ExecutionAccounting } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export async function safeJson<T>(res: Response, fallback: T): Promise<T> {
  if (!res.ok) return fallback;
  const ct = res.headers.get("content-type");
  if (!ct || !ct.includes("application/json")) return fallback;
  try {
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

export async function getPortfolio(): Promise<PortfolioSnapshot | null> {
  try {
    const res = await fetch(`${API_BASE}/api/portfolio`);
    return await safeJson<PortfolioSnapshot | null>(res, null);
  } catch {
    return null;
  }
}

export async function getPositions(): Promise<TradeRecord[]> {
  try {
    const res = await fetch(`${API_BASE}/api/positions`);
    return await safeJson<TradeRecord[]>(res, []);
  } catch {
    return [];
  }
}

export async function getTrades(market: Market = "spot", signal?:AbortSignal): Promise<TradeRecord[]> {
  const res = await fetch(`${API_BASE}/api/trades?market=${market}`,{cache:'no-store',signal});
  if(!res.ok)throw new Error('Trade ledger unavailable');
  return res.json();
}

export async function getTradeHistory(market: Market = "spot", signal?:AbortSignal): Promise<TradeRecord[]> {
  const res = await fetch(`${API_BASE}/api/trades/history?market=${market}`,{cache:'no-store',signal});
  if(!res.ok)throw new Error('Trade history unavailable');
  return res.json();
}

export async function getSignals(): Promise<MarketSignal[]> {
  try {
    const res = await fetch(`${API_BASE}/api/signals`);
    return await safeJson<MarketSignal[]>(res, []);
  } catch {
    return [];
  }
}

export async function getAuditTrail(): Promise<Record<string, unknown>[]> {
  try {
    const res = await fetch(`${API_BASE}/api/audit`);
    return await safeJson<Record<string, unknown>[]>(res, []);
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Binance Exchange Live Market Data & Execution Client
// ---------------------------------------------------------------------------

export interface ExchangeAccount {
  equity: number;
  buying_power: number;
  cash: number;
  portfolio_value: number;
  status: string;
  currency: string;
  balances?: Record<string, { free: number; locked: number; total: number; value_usdt?: number }>;
}

export interface ExchangePosition extends ExecutionAccounting {
  market?: Market;
  stale?: boolean;
  id?: string;
  trade_id?: string;
  symbol: string;
  qty: number;
  side: "LONG" | "SHORT";
  current_price: number | null;
  avg_entry_price: number;
  market_value: number | null;
  cost_basis: number;
  unrealized_pl: number | null;
  unrealized_plpc: number | null;
  take_profit_price?: number;
  stop_loss_price?: number;
  strategy?: string;
  order_type?: string;
}

export interface ExchangeOrder {
  market?: Market;
  trade_id?: string;
  client_order_id?: string;
  id: string;
  symbol: string;
  qty: number;
  side: string;
  type: string;
  status: string;
  filled_avg_price?: number;
  limit_price?: number;
  stop_price?: number;
  order_class?: string;
  time_in_force?: string;
  created_at: string;
}

export interface ExchangeQuote {
  symbol: string;
  bid: number;
  ask: number;
  last: number;
  spread: number;
  bid_size?: number;
  ask_size?: number;
  high_24h?: number;
  low_24h?: number;
  volume_24h?: number;
  price_change_24h?: number;
  price_change_percent_24h?: number;
  timestamp: string;
}

export interface ExchangeBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// Compatibility Type Aliases
export type AlpacaAccount = ExchangeAccount;
export type AlpacaPosition = ExchangePosition;
export type AlpacaOrder = ExchangeOrder;
export type AlpacaQuote = ExchangeQuote;
export type AlpacaBar = ExchangeBar;

export async function getExchangeAccount(market: Market = "spot"): Promise<ExchangeAccount | null> {
  try {return await safeJson<ExchangeAccount|null>(await fetch(`${API_BASE}/api/market/account?market=${market}`),null);}catch{return null;}
}
export const getAlpacaAccount = getExchangeAccount;

export async function getExchangePositions(): Promise<ExchangePosition[]> {
  try {
    const res = await fetch(`${API_BASE}/api/exchange/positions`);
    return await safeJson<ExchangePosition[]>(res, []);
  } catch {
    return [];
  }
}
export const getAlpacaPositions = getExchangePositions;

export async function getExchangeOrders(): Promise<ExchangeOrder[]> {
  try {
    const res = await fetch(`${API_BASE}/api/exchange/orders`);
    return await safeJson<ExchangeOrder[]>(res, []);
  } catch {
    return [];
  }
}
export const getAlpacaOrders = getExchangeOrders;

export async function getExchangeQuote(symbol: string, market: Market = "spot"): Promise<ExchangeQuote | null> {
  try {const response=await fetch(`${API_BASE}/api/market/quote?symbol=${encodeURIComponent(symbol)}&market=${market}`);const data=await safeJson<{price:number;symbol:string;timestamp:string}|null>(response,null);return data&&data.price>0?{symbol:data.symbol,last:data.price,timestamp:data.timestamp,bid:NaN,ask:NaN,spread:NaN}:null;}catch{return null;}
}
export const getAlpacaQuote = getExchangeQuote;

export async function getExchangeBars(symbol: string, timeframe: string = "1H"): Promise<ExchangeBar[]> {
  try {
    const res = await fetch(`${API_BASE}/api/exchange/bars?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`);
    return await safeJson<ExchangeBar[]>(res, []);
  } catch {
    return [];
  }
}
export const getAlpacaBars = getExchangeBars;

export interface ExchangeOrderResponse {
  success: boolean;
  order_id?: string;
  symbol?: string;
  status?: string;
  order_type?: string;
  entry_price?: number;
  limit_price?: number;
  qty?: number;
  side?: string;
  message?: string;
  error?: string;
}
export type AlpacaOrderResponse = ExchangeOrderResponse;

export interface ExchangeCloseResponse {
  success: boolean;
  symbol?: string;
  status?: string;
  error?: string;
}
export type AlpacaCloseResponse = ExchangeCloseResponse;

export interface BotTradeResponse {
  success: boolean;
  symbol?: string;
  strategy?: string;
  decision?: string;
  consensus_score?: number;
  binance_order_id?: string;
  alpaca_order_id?: string;
  entry_price?: number;
  take_profit_price?: number;
  stop_loss_price?: number;
  take_profit_pct?: number;
  stop_loss_pct?: number;
  tp_reason?: string;
  sl_reason?: string;
  risk_reward_ratio?: number;
  score?: number;
  status_label?: string;
  reasons?: string[];
  order_type?: string;
  note?: string;
  error?: string;
}

export async function submitExchangeOrder(
  symbol: string,
  qty: number,
  side: "buy" | "sell",
  order_type: "market" | "limit" = "market",
  limit_price?: number,
  quote_quantity?: number
): Promise<ExchangeOrderResponse> {
  try {
    const res = await fetch(`${API_BASE}/api/exchange/order`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, qty, side, order_type, limit_price, quote_quantity }),
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      return { success: false, error: errJson.detail || `Server error: HTTP ${res.status}` };
    }
    return await safeJson<ExchangeOrderResponse>(res, { success: false });
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : "Failed to submit order";
    return { success: false, error: message };
  }
}
export const submitAlpacaOrder = submitExchangeOrder;

export async function fillPendingTrade(tradeId: string, fillPrice?: number, market: Market = "spot"): Promise<{ success: boolean; message?: string; error?: string }> {
  try {
    const res = await fetch(`${API_BASE}/api/trades/${encodeURIComponent(tradeId)}/fill?market=${market}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fillPrice === undefined ? {} : { fill_price: fillPrice }),
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      return { success: false, error: errJson.detail || `Server error: HTTP ${res.status}` };
    }
    return await safeJson(res, { success: false });
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : "Network error";
    return { success: false, error: message };
  }
}

export async function getMarketStatus(): Promise<MarketClockStatus> {
  const fallback: MarketClockStatus = {
    is_open: true,
    current_time_et: "",
    market: "CRYPTO_24_7",
    exchange: "BINANCE",
    reason: "24/7 Crypto Session Active",
  };
  try {
    const res = await fetch(`${API_BASE}/api/market-status`);
    return await safeJson<MarketClockStatus>(res, fallback);
  } catch {
    return fallback;
  }
}

export async function closeExchangePosition(symbol: string, market: Market = "spot", trade_id?: string): Promise<ExchangeCloseResponse> {
  try {
    const res = await fetch(`${API_BASE}/api/exchange/close-position`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, market, trade_id }),
    });
    return await safeJson<ExchangeCloseResponse>(res, { success: false });
  } catch {
    return { success: false };
  }
}
export const closeAlpacaPosition = closeExchangePosition;

export async function cancelExchangeOrder(orderId: string, market: Market = "spot", symbol?: string): Promise<{ success: boolean; error?: string }> {
  try {
    const res = await fetch(`${API_BASE}/api/exchange/orders/${encodeURIComponent(orderId)}?market=${market}${symbol ? `&symbol=${encodeURIComponent(symbol)}` : ""}`, {
      method: "DELETE",
    });
    return await safeJson(res, { success: false });
  } catch {
    return { success: false };
  }
}
export const cancelAlpacaOrder = cancelExchangeOrder;

export async function cancelAllExchangeOrders(market: Market = "spot"): Promise<{ success: boolean; cancelled?: number; error?: string }> {
  try {
    const res = await fetch(`${API_BASE}/api/exchange/cancel-all?market=${market}`, {
      method: "POST",
    });
    return await safeJson(res, { success: false });
  } catch {
    return { success: false };
  }
}
export const cancelAllAlpacaOrders = cancelAllExchangeOrders;

export interface OrderFlowData {
  success: boolean;
  gamma_profile?: {
    regime?: string;
    call_wall?: number;
    put_wall?: number;
    abs_gamma?: number;
  };
  order_flow?: {
    symbol: string;
    current_price: number | null;
    trend_bias: string;
    nearest_bullish_ob?: { low: number; high: number; strength: number };
    nearest_bearish_ob?: { low: number; high: number; strength: number };
    unfilled_fvgs?: { gap_type: string; top: number; bottom: number; size: number }[];
    liquidity_heatmap?: { price: number; volume: number; side: string; intensity: number }[];
  };
}

export async function getOrderFlowAnalytics(symbol: string): Promise<OrderFlowData> {
  try {
    const res = await fetch(`${API_BASE}/api/analytics/order-flow?symbol=${encodeURIComponent(symbol)}`);
    return await safeJson<OrderFlowData>(res, { success: false });
  } catch {
    return { success: false };
  }
}

export async function executeBotTrade(
  symbol: string,
  strategy: string = "MASTER_ORDER_FLOW",
  riskFraction: number = 0.8,
  takeProfitPct?: number,
  stopLossPct?: number
): Promise<BotTradeResponse> {
  try {
    const res = await fetch(`${API_BASE}/api/bot/execute-trade`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol,
        strategy,
        risk_fraction: riskFraction,
        take_profit_pct: takeProfitPct,
        stop_loss_pct: stopLossPct,
      }),
    });
    return await safeJson<BotTradeResponse>(res, { success: false });
  } catch {
    return { success: false };
  }
}

export interface AutoTradingStatus {
  is_running: boolean;
  interval_seconds: number;
  max_open_positions: number;
  watched_symbols: string[];
  total_automated_trades: number;
  last_run_timestamp?: string;
  last_trade_result?: Record<string, unknown>;
  last_log?: string;
  guardian_active?: boolean;
  scanner_diagnostics?: Record<string, {
    symbol: string;
    is_valid: boolean;
    score: number;
    status_label: string;
    reasons: string[];
    levels?: {
      entry_price: number;
      take_profit_price: number;
      stop_loss_price: number;
      take_profit_pct: number;
      stop_loss_pct: number;
      tp_reason: string;
      sl_reason: string;
      risk_reward_ratio: number;
    };
  }>;
}

export async function getAutoTradingStatus(): Promise<AutoTradingStatus|null> {
  try {
    return await safeJson<AutoTradingStatus|null>(await fetch(`${API_BASE}/api/bot/auto-trading/status`,{cache:'no-store'}),null);
  } catch { return null; }
}

export async function startAutoTrading(interval: number = 30): Promise<{ success: boolean; message?: string }> {
  try {
    const res = await fetch(`${API_BASE}/api/bot/auto-trading/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interval }),
    });
    return await safeJson(res, { success: false });
  } catch {
    return { success: false };
  }
}

export async function stopAutoTrading(): Promise<{ success: boolean; message?: string }> {
  try {
    const res = await fetch(`${API_BASE}/api/bot/auto-trading/stop`, {
      method: "POST",
    });
    return await safeJson(res, { success: false });
  } catch {
    return { success: false };
  }
}

export async function triggerAutoTradingCycle(symbol?: string, market: Market = "spot"): Promise<{
  success: boolean;
  executed?: boolean;
  trade_id?: string;
  symbol?: string;
  reason?: string;
  score?: number;
  status_label?: string;
  reasons?: string[];
  take_profit_price?: number;
  stop_loss_price?: number;
  tp_reason?: string;
  sl_reason?: string;
  risk_reward_ratio?: number;
  scanner_diagnostics?: Record<string, unknown>;
}> {
  try {
    const res = await fetch(`${API_BASE}/api/bot/auto-trading/trigger-cycle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(symbol ? { symbol, market } : {market}),
    });
    return await safeJson(res, { success: false });
  } catch {
    return { success: false };
  }
}
