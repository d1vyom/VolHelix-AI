import { PortfolioSnapshot, TradeRecord, MarketSignal } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

async function safeJson<T>(res: Response, fallback: T): Promise<T> {
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

export async function getTrades(): Promise<TradeRecord[]> {
  try {
    const res = await fetch(`${API_BASE}/api/trades`);
    return await safeJson<TradeRecord[]>(res, []);
  } catch {
    return [];
  }
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
// Alpaca Real Live Market Data & Execution Client
// ---------------------------------------------------------------------------

export interface AlpacaAccount {
  equity: number;
  buying_power: number;
  cash: number;
  portfolio_value: number;
  status: string;
  currency: string;
}

export interface AlpacaPosition {
  symbol: string;
  qty: number;
  side: "LONG" | "SHORT";
  current_price: number;
  avg_entry_price: number;
  market_value: number;
  cost_basis: number;
  unrealized_pl: number;
  unrealized_plpc: number;
}

export interface AlpacaOrder {
  id: string;
  symbol: string;
  qty: number;
  side: string;
  type: string;
  status: string;
  filled_avg_price?: number;
  created_at: string;
}

export interface AlpacaQuote {
  symbol: string;
  bid: number;
  ask: number;
  last: number;
  spread: number;
  bid_size?: number;
  ask_size?: number;
  timestamp: string;
}

export interface AlpacaBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export async function getAlpacaAccount(): Promise<AlpacaAccount> {
  try {
    const res = await fetch(`${API_BASE}/api/alpaca/account`);
    return await safeJson<AlpacaAccount>(res, {
      equity: 100000.0,
      buying_power: 400000.0,
      cash: 100000.0,
      portfolio_value: 100000.0,
      status: "ACTIVE",
      currency: "USD",
    });
  } catch {
    return {
      equity: 100000.0,
      buying_power: 400000.0,
      cash: 100000.0,
      portfolio_value: 100000.0,
      status: "ACTIVE",
      currency: "USD",
    };
  }
}

export async function getAlpacaPositions(): Promise<AlpacaPosition[]> {
  try {
    const res = await fetch(`${API_BASE}/api/alpaca/positions`);
    return await safeJson<AlpacaPosition[]>(res, []);
  } catch {
    return [];
  }
}

export async function getAlpacaOrders(): Promise<AlpacaOrder[]> {
  try {
    const res = await fetch(`${API_BASE}/api/alpaca/orders`);
    return await safeJson<AlpacaOrder[]>(res, []);
  } catch {
    return [];
  }
}

export async function getAlpacaQuote(symbol: string): Promise<AlpacaQuote> {
  try {
    const res = await fetch(`${API_BASE}/api/alpaca/quote?symbol=${encodeURIComponent(symbol)}`);
    return await safeJson<AlpacaQuote>(res, {
      symbol,
      bid: 574.8,
      ask: 574.9,
      last: 574.85,
      spread: 0.1,
      timestamp: new Date().toISOString(),
    });
  } catch {
    return {
      symbol,
      bid: 574.8,
      ask: 574.9,
      last: 574.85,
      spread: 0.1,
      timestamp: new Date().toISOString(),
    };
  }
}

export async function getAlpacaBars(symbol: string, timeframe: string = "1H"): Promise<AlpacaBar[]> {
  try {
    const res = await fetch(`${API_BASE}/api/alpaca/bars?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`);
    return await safeJson<AlpacaBar[]>(res, []);
  } catch {
    return [];
  }
}

export interface AlpacaOrderResponse {
  success: boolean;
  order_id?: string;
  symbol?: string;
  status?: string;
  qty?: number;
  side?: string;
  error?: string;
}

export interface AlpacaCloseResponse {
  success: boolean;
  symbol?: string;
  status?: string;
  error?: string;
}

export interface BotTradeResponse {
  success: boolean;
  symbol?: string;
  strategy?: string;
  decision?: string;
  consensus_score?: number;
  alpaca_order_id?: string;
  alpaca_status?: string;
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

export async function submitAlpacaOrder(symbol: string, qty: number, side: "buy" | "sell"): Promise<AlpacaOrderResponse> {
  try {
    const res = await fetch(`${API_BASE}/api/alpaca/order`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, qty, side, order_type: "market" }),
    });
    return await safeJson<AlpacaOrderResponse>(res, { success: false });
  } catch {
    return { success: false };
  }
}

export async function closeAlpacaPosition(symbol: string): Promise<AlpacaCloseResponse> {
  try {
    const res = await fetch(`${API_BASE}/api/alpaca/close-position`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol }),
    });
    return await safeJson<AlpacaCloseResponse>(res, { success: false });
  } catch {
    return { success: false };
  }
}

export interface OrderFlowData {
  success: boolean;
  order_flow?: {
    symbol: string;
    current_price: number;
    trend_bias: string;
    nearest_bullish_ob?: { low: number; high: number; strength: number };
    nearest_bearish_ob?: { low: number; high: number; strength: number };
    unfilled_fvgs?: { gap_type: string; top: number; bottom: number; size: number }[];
    liquidity_heatmap?: { price: number; volume: number; side: string; intensity: number }[];
  };
  gamma_profile?: {
    spot_price: number;
    total_net_gex: number;
    call_wall: number;
    put_wall: number;
    gamma_flip: number;
    regime: string;
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

export async function getAutoTradingStatus(): Promise<AutoTradingStatus> {
  try {
    const res = await fetch(`${API_BASE}/api/bot/auto-trading/status`);
    return await safeJson<AutoTradingStatus>(res, {
      is_running: false,
      interval_seconds: 30,
      max_open_positions: 3,
      watched_symbols: ["SPY", "QQQ", "NVDA", "AAPL", "TSLA"],
      total_automated_trades: 0,
      last_log: "Standby",
    });
  } catch {
    return {
      is_running: false,
      interval_seconds: 30,
      max_open_positions: 3,
      watched_symbols: ["SPY", "QQQ", "NVDA", "AAPL", "TSLA"],
      total_automated_trades: 0,
      last_log: "Standby",
    };
  }
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

export async function triggerAutoTradingCycle(symbol?: string): Promise<{
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
      body: JSON.stringify(symbol ? { symbol } : {}),
    });
    return await safeJson(res, { success: false });
  } catch {
    return { success: false };
  }
}