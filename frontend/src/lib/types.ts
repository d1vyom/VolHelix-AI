export type Regime = "LOW_VOL" | "NORMAL" | "ELEVATED" | "SQUEEZE" | "CRISIS";
export type Trend = "BULLISH" | "BEARISH" | "NEUTRAL";
// VolHelix executes exactly one strategy. CASH is the explicit risk-off state
// (hold USDT, no order) rather than a competing strategy.
export type StrategyType = "MASTER_ORDER_FLOW" | "CASH";

export type TradeStatus = "PENDING" | "OPEN" | "CLOSED" | "STOPPED_OUT" | "TAKE_PROFIT" | "CANCELLED" | "FILLED" | string;
export type OrderType = "MARKET" | "LIMIT";
export type OrderSide = "BUY" | "SELL";

// ── Watched Crypto Symbols ──
export type WatchedSymbol = "BTCUSDT" | "ETHUSDT" | "SOLUSDT" | "BNBUSDT" | "XRPUSDT";
export const WATCHED_SYMBOLS: WatchedSymbol[] = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];
export const DEFAULT_SYMBOL: WatchedSymbol = "BTCUSDT";

export const SYMBOL_DISPLAY: Record<WatchedSymbol, { name: string; icon: string }> = {
  BTCUSDT: { name: "Bitcoin", icon: "BTC" },
  ETHUSDT: { name: "Ethereum", icon: "ETH" },
  SOLUSDT: { name: "Solana", icon: "SOL" },
  BNBUSDT: { name: "BNB", icon: "BNB" },
  XRPUSDT: { name: "XRP", icon: "XRP" },
};

export interface CryptoAssetBalance {
  asset: string;
  free: number;
  locked: number;
  total: number;
  value_usdt: number;
}

export interface OptionLeg {
  action: "BUY" | "SELL";
  contract_type: "CALL" | "PUT";
  strike: number;
  expiry: string;
  symbol: string;
  premium: number;
  delta?: number;
  gamma?: number;
  theta?: number;
  vega?: number;
  oi?: number;
  bid?: number;
  ask?: number;
}

export interface TradeProposal {
  id: string;
  symbol?: string;
  underlying: string;
  strategy_type: StrategyType;
  legs?: OptionLeg[];
  is_credit?: boolean;
  net_premium?: number;
  max_profit?: number;
  max_loss?: number;
  breakevens?: number[];
  net_delta?: number;
  net_theta?: number;
  net_vega?: number;
  dte?: number;
  ev?: number;
  thesis?: string;
  regime_at_entry?: string;
  take_profit?: number;
  stop_loss?: number;
  order_type?: string;
  limit_price?: number;
  side?: string;
  qty?: number;
  quote_qty?: number;
  entry_price?: number;
  confidence?: number;
}

export interface TradeRecord {
  trade_id: string;
  proposal: TradeProposal;
  status: TradeStatus;
  entry_time?: string;
  exit_time?: string;
  realized_pnl?: number;
  unrealized_pnl?: number;
  take_profit_price?: number;
  stop_loss_price?: number;
  exit_price?: number;
  current_price?: number;
  entry_price?: number;
  binance_order_id?: string;
  commission?: number;
  commission_asset?: string;
  id?: string;
  symbol?: string;
  strategy?: string;
  side?: string;
  qty?: number;
  timestamp?: string;
}

// Crypto trades 24/7: this clock is informational and never gates execution.
export interface MarketClockStatus {
  is_open: boolean;
  current_time_et: string;
  current_time_utc?: string;
  market?: string;
  exchange?: string;
  next_open?: string;
  next_close?: string;
  reason: string;
}

export interface PortfolioSnapshot {
  timestamp: string;
  equity: number;
  buying_power: number;
  daily_pnl: number;
  daily_pnl_pct?: number;
  total_pnl: number;
  total_pnl_pct?: number;
  open_positions: number;
  open_position_count?: number;
  balances?: Record<string, CryptoAssetBalance>;
  net_delta: number;
  net_theta: number;
  net_vega: number;
  current_regime: Regime;
  exposures: Record<string, number>;
  exposure_by_symbol?: Record<string, number>;
}

export interface MarketSignal {
  timestamp: string;
  symbol?: string;
  underlying: string;
  price: number;
  price_change_24h?: number;
  volume_24h?: number;
  high_24h?: number;
  low_24h?: number;
  iv_current: number;
  iv_rank: number;
  iv_percentile: number;
  regime: Regime;
  trend: Trend;
  thesis: string;
  confidence: number;
}

export interface CheckResult {
  passed: boolean;
  detail: string;
}

export interface RiskGateResult {
  approved: boolean;
  reason: string;
  checks: Record<string, CheckResult>;
  timestamp: string;
}

export interface AgentVote {
  agent_name: string;
  vote: "AGREE" | "DISAGREE";
  confidence: number;
  reasoning: string;
}

export interface DebateResult {
  proposal_id: string;
  votes: AgentVote[];
  consensus_reached: boolean;
  consensus_score: number;
  winning_proposal_id?: string;
  summary: string;
}
