export interface StreamHealth {
  symbol: string;
  connected: boolean;
  streams: string[];
  last_trade_ts: number;
  last_book_ts: number;
  gap_events: number;
  book_resyncs: number;
  lag_ms: number;
  status: "LIVE" | "DEGRADED" | "DISCONNECTED" | "DISABLED";
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
  absorption: "BUY_ABSORBED" | "SELL_ABSORBED" | null;
  tick_group: number;
}

export interface TapeEntry {
  ts: number;
  price: number;
  qty: number;
  quote_qty: number;
  side: "BUY" | "SELL";
  is_whale: boolean;
  size_bucket: "S" | "M" | "L" | "XL";
  price_tick: "UP" | "DOWN" | "SAME";
  aggressive_streak: number;
}

export interface LadderLevel {
  price: number;
  bid_size: number;
  ask_size: number;
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
  walls: Record<string, unknown>[];
  levels: LadderLevel[];
}

export interface HeatmapFrame {
  ts_bin: number;
  levels: [number, number, number][]; // price, bid, ask
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
  walls: Record<string, unknown>[];
}

export interface FlowMetrics {
  symbol: string;
  ts: number;
  price: number;
  session_cvd: number;
  bar_delta: number;
  delta_percent: number;
  cvd_slope: number;
  cvd_divergence: "BEARISH" | "BULLISH" | null;
  buy_sell_ratio: number;
  aggression_index: number;
  absorption_flag: "BUY_ABSORBED" | "SELL_ABSORBED" | null;
  stacked_imbalance_bias: "BUY" | "SELL" | "NEUTRAL";
  poc_price: number;
  vah: number;
  val: number;
  price_vs_value: "ABOVE_VALUE" | "IN_VALUE" | "BELOW_VALUE";
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
  mode: "SESSION" | "VISIBLE" | "FIXED_RANGE";
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
  divergence: "BEARISH" | "BULLISH" | null;
}
