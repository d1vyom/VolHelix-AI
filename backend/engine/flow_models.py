from typing import Any, Literal
from pydantic import BaseModel, Field
from backend.marketdata.models import LadderLevel, StreamHealth

class FootprintCell(BaseModel):
    """
    Price-bucketed trade volume cluster cell inside a single bar.
    Note: buy_volume corresponds to OrderflowChart bid_size (executed at ask/buy aggressor).
    sell_volume corresponds to OrderflowChart ask_size (executed at bid/sell aggressor).
    """
    price: float = Field(description="Lower bound price of bucket, rounded to grouped tick")
    buy_volume: float = Field(default=0.0, description="Executed buy volume from aggressive market buys")
    sell_volume: float = Field(default=0.0, description="Executed sell volume from aggressive market sells")
    total_volume: float = Field(default=0.0, description="Total traded volume in this price bucket")
    delta: float = Field(default=0.0, description="Delta volume (buy_volume - sell_volume)")
    trades: int = Field(default=0, description="Count of individual aggregated trades in this bucket")
    buy_imbalance: bool = Field(default=False, description="Diagonal buy imbalance vs sell volume at level below")
    sell_imbalance: bool = Field(default=False, description="Diagonal sell imbalance vs buy volume at level above")

class FootprintBar(BaseModel):
    """A complete candlestick bar enriched with price-level footprint clusters and delta studies."""
    symbol: str = Field(description="Uppercase trading pair symbol")
    interval: str = Field(description="Candlestick interval (e.g. '1m', '5m', '15m')")
    open_time: int = Field(description="Bar open timestamp in ms epoch")
    close_time: int = Field(description="Bar close timestamp in ms epoch")
    open: float = Field(description="Bar open price")
    high: float = Field(description="Bar high price")
    low: float = Field(description="Bar low price")
    close: float = Field(description="Bar close / last price")
    volume: float = Field(default=0.0, description="Total bar base asset volume")
    is_closed: bool = Field(default=False, description="True if bar interval is finalized")
    cells: list[FootprintCell] = Field(default_factory=list, description="Footprint cells sorted ascending by price")
    delta: float = Field(default=0.0, description="Net bar volume delta (sum of cell deltas)")
    cumulative_delta: float = Field(default=0.0, description="CVD at bar close timestamp")
    max_delta: float = Field(default=0.0, description="Maximum intra-bar delta reached")
    min_delta: float = Field(default=0.0, description="Minimum intra-bar delta reached")
    delta_percent: float = Field(default=0.0, description="Delta relative to volume (delta / volume)")
    poc_price: float = Field(default=0.0, description="Point of Control (price level with highest volume)")
    vah: float = Field(default=0.0, description="Value Area High price level")
    val: float = Field(default=0.0, description="Value Area Low price level")
    value_area_volume: float = Field(default=0.0, description="Total volume contained within VAH-VAL")
    stacked_buy_imbalance_zones: list[list[float]] = Field(
        default_factory=list,
        description="Zones of >= N consecutive buy imbalances as [low_price, high_price]"
    )
    stacked_sell_imbalance_zones: list[list[float]] = Field(
        default_factory=list,
        description="Zones of >= N consecutive sell imbalances as [low_price, high_price]"
    )
    is_naked_poc: bool = Field(default=False, description="True if this bar's POC has not been tested by later price action")
    absorption: Literal["BUY_ABSORBED", "SELL_ABSORBED"] | None = Field(
        default=None,
        description="Detected absorption pattern or None"
    )
    tick_group: float = Field(default=1.0, description="Price bucket grouping size applied to this bar")

class VolumeProfileLevel(BaseModel):
    """Aggregated volume profile level with delta breakdown."""
    price: float = Field(description="Grouped price level")
    buy_volume: float = Field(default=0.0, description="Aggressive buy volume at price")
    sell_volume: float = Field(default=0.0, description="Aggressive sell volume at price")
    total_volume: float = Field(default=0.0, description="Total volume traded at price")
    delta: float = Field(default=0.0, description="Net volume delta (buy - sell)")
    is_poc: bool = Field(default=False, description="True if this level is the Point of Control")
    in_value_area: bool = Field(default=False, description="True if within 70% value area")

class VolumeProfileSnapshot(BaseModel):
    """Volume profile snapshot over session or visible range."""
    symbol: str = Field(description="Trading pair symbol")
    mode: Literal["SESSION", "VISIBLE", "FIXED_RANGE"] = Field(description="Aggregation scope mode")
    start_ts: int = Field(description="Start time of window in ms epoch")
    end_ts: int = Field(description="End time of window in ms epoch")
    tick_group: float = Field(description="Tick grouping applied to profile levels")
    levels: list[VolumeProfileLevel] = Field(default_factory=list, description="Volume profile levels ascending")
    poc_price: float = Field(default=0.0, description="Point of Control price")
    vah: float = Field(default=0.0, description="Value Area High price")
    val: float = Field(default=0.0, description="Value Area Low price")
    total_volume: float = Field(default=0.0, description="Total volume across profile")
    naked_pocs: list[float] = Field(default_factory=list, description="Unfilled prior session/period POCs")

class CVDPoint(BaseModel):
    """Time-series point for Cumulative Volume Delta and divergence detection."""
    ts: int = Field(description="Timestamp in ms epoch")
    cvd: float = Field(description="Cumulative volume delta value")
    delta: float = Field(description="Period delta value")
    price: float = Field(description="Reference asset price at timestamp")
    divergence: Literal["BEARISH", "BULLISH"] | None = Field(
        default=None,
        description="Detected CVD divergence at this point"
    )

class TapeEntry(BaseModel):
    """Enriched Time & Sales print with aggression streak and whale detection."""
    ts: int = Field(description="Trade execution timestamp in ms epoch")
    price: float = Field(description="Executed price")
    qty: float = Field(description="Executed quantity in base units")
    quote_qty: float = Field(description="Executed notional in USD")
    side: Literal["BUY", "SELL"] = Field(description="Aggressor side")
    is_whale: bool = Field(default=False, description="True if print exceeds whale notional threshold or percentile")
    size_bucket: Literal["S", "M", "L", "XL"] = Field(default="S", description="Relative order size category")
    price_tick: Literal["UP", "DOWN", "SAME"] = Field(default="SAME", description="Price change tick direction vs prior trade")
    aggressive_streak: int = Field(default=1, description="Count of consecutive prints on the same side")

class HeatmapFrame(BaseModel):
    """Single time slice snapshot of resting book liquidity."""
    ts_bin: int = Field(description="Timestamp bin in ms epoch")
    levels: list[list[float]] = Field(
        default_factory=list,
        description="List of [price, bid_size, ask_size] entries"
    )

class HeatmapSnapshot(BaseModel):
    """Historical resting liquidity matrix for Canvas 2D heatmap rendering."""
    symbol: str = Field(description="Trading pair symbol")
    tick_group: float = Field(description="Price tick grouping applied")
    bin_ms: int = Field(description="Time bin resolution in ms")
    window_sec: int = Field(description="Total window history in seconds")
    price_min: float = Field(description="Lowest price bucket in window")
    price_max: float = Field(description="Highest price bucket in window")
    max_size: float = Field(description="99th percentile size normalizer for color scale")
    frames: list[HeatmapFrame] = Field(default_factory=list, description="Time-ordered liquidity frames")
    walls: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Detected persistent liquidity walls: [{price, size, side, age_sec, persistence}]"
    )

class DomAnalytics(BaseModel):
    """Depth of Market analytics and ladder levels."""
    symbol: str = Field(description="Trading pair symbol")
    best_bid: float = Field(description="Highest current bid price")
    best_ask: float = Field(description="Lowest current ask price")
    spread: float = Field(description="Bid-ask spread in price units")
    spread_bps: float = Field(description="Bid-ask spread in basis points")
    mid: float = Field(description="Mid market price")
    bid_depth_n: float = Field(description="Cumulative bid depth across top N levels")
    ask_depth_n: float = Field(description="Cumulative ask depth across top N levels")
    book_imbalance: float = Field(description="Depth imbalance: (bid_depth - ask_depth) / (bid_depth + ask_depth)")
    walls: list[dict[str, Any]] = Field(default_factory=list, description="Active liquidity walls detected in book")
    levels: list[LadderLevel] = Field(default_factory=list, description="Grouped ladder levels around mid price")

class FlowMetrics(BaseModel):
    """Comprehensive real-time order flow telemetry consumed by trading agents and UI."""
    symbol: str = Field(description="Trading pair symbol")
    ts: int = Field(description="Snapshot timestamp in ms epoch")
    price: float = Field(description="Current market price")
    session_cvd: float = Field(description="Cumulative volume delta anchored at 00:00 UTC")
    bar_delta: float = Field(description="Current forming bar volume delta")
    delta_percent: float = Field(description="Current forming bar delta percentage of total volume")
    cvd_slope: float = Field(description="Normalized least-squares slope of CVD over recent points")
    cvd_divergence: Literal["BEARISH", "BULLISH"] | None = Field(default=None, description="Active CVD divergence flag")
    buy_sell_ratio: float = Field(description="Rolling 1-minute aggressor volume ratio (buy_volume / sell_volume)")
    aggression_index: float = Field(description="Ratio of volume from whale prints vs total volume (0.0 - 1.0)")
    absorption_flag: Literal["BUY_ABSORBED", "SELL_ABSORBED"] | None = Field(default=None, description="Detected absorption state")
    stacked_imbalance_bias: Literal["BUY", "SELL", "NEUTRAL"] = Field(description="Institutional directional bias from stacked zones")
    poc_price: float = Field(description="Current bar Point of Control")
    vah: float = Field(description="Current bar Value Area High")
    val: float = Field(description="Current bar Value Area Low")
    price_vs_value: Literal["ABOVE_VALUE", "IN_VALUE", "BELOW_VALUE"] = Field(description="Current price location relative to Value Area")
    book_imbalance: float = Field(description="Top-20 book depth imbalance (-1.0 to +1.0)")
    spread_bps: float = Field(description="Current bid-ask spread in basis points")
    nearest_bid_wall: float | None = Field(default=None, description="Price of closest large resting bid wall below market")
    nearest_ask_wall: float | None = Field(default=None, description="Price of closest large resting ask wall above market")
    vwap: float = Field(description="Session anchored VWAP (00:00 UTC)")
    vwap_upper_1: float = Field(description="VWAP + 1 standard deviation band")
    vwap_lower_1: float = Field(description="VWAP - 1 standard deviation band")
    trade_rate: float = Field(description="Incoming trade rate in trades per second")
    volume_rate: float = Field(description="Incoming base asset volume rate per second")
    health: StreamHealth = Field(description="Underlying market stream connectivity health")
