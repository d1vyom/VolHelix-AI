export type Regime = "LOW_VOL" | "NORMAL" | "ELEVATED" | "SQUEEZE" | "CRISIS";
export type Trend = "BULLISH" | "BEARISH" | "NEUTRAL";
export type StrategyType = 
  | "MASTER_ORDER_FLOW"
  | "BULL_PUT_SPREAD" 
  | "BEAR_CALL_SPREAD" 
  | "IRON_CONDOR" 
  | "LONG_STRADDLE" 
  | "CALENDAR_SPREAD" 
  | "PROTECTIVE_PUT" 
  | "CASH";

export type TradeStatus = "PENDING" | "OPEN" | "CLOSED" | "STOPPED_OUT" | "TAKE_PROFIT" | "CANCELLED" | "FILLED" | string;
export type OrderType = "MARKET" | "LIMIT";

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
  underlying: string;
  strategy_type: StrategyType;
  legs: OptionLeg[];
  is_credit: boolean;
  net_premium: number;
  max_profit: number;
  max_loss: number;
  breakevens: number[];
  net_delta: number;
  net_theta: number;
  net_vega: number;
  dte: number;
  ev: number;
  thesis: string;
  regime_at_entry?: string;
  take_profit?: number;
  stop_loss?: number;
  order_type?: string;
  limit_price?: number;
  side?: string;
  qty?: number;
}

export interface TradeRecord {
  trade_id: string;
  proposal: TradeProposal;
  status: TradeStatus;
  entry_time: string;
  exit_time?: string;
  realized_pnl?: number;
  take_profit_price?: number;
  stop_loss_price?: number;
  exit_price?: number;
  current_price?: number;
  id?: string;
  symbol?: string;
  strategy?: string;
  side?: string;
  qty?: number;
  entry_price?: number;
  timestamp?: string;
}

export interface MarketClockStatus {
  is_open: boolean;
  raw_is_open: boolean;
  simulation_active: boolean;
  simulation_override?: boolean;
  current_time_et: string;
  next_open?: string;
  next_close?: string;
  reason: string;
}

export interface PortfolioSnapshot {
  timestamp: string;
  equity: number;
  buying_power: number;
  daily_pnl: number;
  total_pnl: number;
  open_positions: number;
  net_delta: number;
  net_theta: number;
  net_vega: number;
  current_regime: Regime;
  exposures: Record<string, number>;
}

export interface MarketSignal {
  timestamp: string;
  underlying: string;
  price: number;
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
