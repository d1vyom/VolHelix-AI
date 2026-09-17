/**
 * Order Flow Type Definitions
 * Exact 1:1 mirror of backend Pydantic models in snake_case.
 * Wire format contract — do NOT rename to camelCase.
 */

export type AggressorSide = "BUY" | "SELL";
export type StreamStatus = "LIVE" | "DEGRADED" | "DISCONNECTED" | "DISABLED";
export type SnapshotSource = "REST" | "PARTIAL_STREAM" | "MAINTAINED";
export type ProfileMode = "SESSION" | "VISIBLE" | "FIXED_RANGE";
export type DivergenceType = "BEARISH" | "BULLISH";
export type SizeBucket = "S" | "M" | "L" | "XL";
export type PriceTick = "UP" | "DOWN" | "SAME";
export type AbsorptionType = "BUY_ABSORBED" | "SELL_ABSORBED";
export type PriceVsValue = "ABOVE_VALUE" | "IN_VALUE" | "BELOW_VALUE";
export type StackedImbalanceBias = "BUY" | "SELL" | "NEUTRAL";

export interface Trade {
  symbol: string;
  agg_id: number;
  price: number;
  qty: number;
  quote_qty: number;
  ts: number;
  is_buyer_maker: boolean;
  side: AggressorSide;
  first_id: number;
  last_id: number;
}

export interface BookDelta {
  symbol: string;
  first_update_id: number;
  final_update_id: number;
  bids: [number, number][];
  asks: [number, number][];
  event_ts: number;
}

export interface BookSnapshot {
  symbol: string;
  last_update_id: number;
  bids: [number, number][];
  asks: [number, number][];
  ts: number;
  source: SnapshotSource;
}

export interface LadderLevel {
  price: number;
  bid_size: number;
  ask_size: number;
  bid_notional: number;
  ask_notional: number;
  is_wall: boolean;
  is_poc: boolean;
  traded_buy: number;
  traded_sell: number;
  depth_pct: number;
}

export interface StreamHealth {
  symbol: string;
  connected: boolean;
  streams: string[];
  last_trade_ts: number;
  last_book_ts: number;
  messages_per_sec: number;
  reconnects: number;
  book_resyncs: number;
  gap_events: number;
  lag_ms: number;
  status: StreamStatus;
}

export interface FootprintCell {
  price: number;
  buy_volume: number;
  sell_volume: number;
  total_volume: number;
  delta: number;
  trades: number;
  buy_imbalance: boolean;
  sell_imbalance: boolean;
}

export interface FootprintBar {
  symbol: string;
  interval: string;
  open_time: number;
  close_time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  is_closed: boolean;
  cells: FootprintCell[];
  delta: number;
  cumulative_delta: number;
  max_delta: number;
  min_delta: number;
  delta_percent: number;
  poc_price: number;
  vah: number;
  val: number;
  value_area_volume: number;
  stacked_buy_imbalance_zones: [number, number][];
  stacked_sell_imbalance_zones: [number, number][];
  is_naked_poc: boolean;
  absorption: AbsorptionType | null;
  tick_group: number;
}

export interface VolumeProfileLevel {
  price: number;
  buy_volume: number;
  sell_volume: number;
  total_volume: number;
  delta: number;
  is_poc: boolean;
  in_value_area: boolean;
}

export interface VolumeProfileSnapshot {
  symbol: string;
  mode: ProfileMode;
  start_ts: number;
  end_ts: number;
  tick_group: number;
  levels: VolumeProfileLevel[];
  poc_price: number;
  vah: number;
  val: number;
  total_volume: number;
  naked_pocs: number[];
}

export interface CVDPoint {
  ts: number;
  cvd: number;
  delta: number;
  price: number;
  divergence: DivergenceType | null;
}

export interface TapeEntry {
  ts: number;
  price: number;
  qty: number;
  quote_qty: number;
  side: AggressorSide;
  is_whale: boolean;
  size_bucket: SizeBucket;
  price_tick: PriceTick;
  aggressive_streak: number;
}

export interface HeatmapFrame {
  ts_bin: number;
  levels: [number, number, number][]; // [price, bid_size, ask_size]
}

export interface HeatmapWall {
  price: number;
  size: number;
  side: "BID" | "ASK";
  age_sec: number;
  persistence: number;
}

export interface HeatmapSnapshot {
  symbol: string;
  tick_group: number;
  bin_ms: number;
  window_sec: number;
  price_min: number;
  price_max: number;
  max_size: number;
  frames: HeatmapFrame[];
  walls: HeatmapWall[];
}

export interface DomAnalytics {
  symbol: string;
  best_bid: number;
  best_ask: number;
  spread: number;
  spread_bps: number;
  mid: number;
  bid_depth_n: number;
  ask_depth_n: number;
  book_imbalance: number;
  walls: HeatmapWall[];
  levels: LadderLevel[];
}

export interface FlowMetrics {
  symbol: string;
  ts: number;
  price: number;
  session_cvd: number;
  bar_delta: number;
  delta_percent: number;
  cvd_slope: number;
  cvd_divergence: DivergenceType | null;
  buy_sell_ratio: number;
  aggression_index: number;
  absorption_flag: AbsorptionType | null;
  stacked_imbalance_bias: StackedImbalanceBias;
  poc_price: number;
  vah: number;
  val: number;
  price_vs_value: PriceVsValue;
  book_imbalance: number;
  spread_bps: number;
  nearest_bid_wall: number | null;
  nearest_ask_wall: number | null;
  vwap: number;
  vwap_upper_1: number;
  vwap_lower_1: number;
  trade_rate: number;
  volume_rate: number;
  health: StreamHealth;
}
