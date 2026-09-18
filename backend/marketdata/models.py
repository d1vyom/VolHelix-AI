from typing import Literal
from pydantic import BaseModel, Field

class Trade(BaseModel):
    """Normalized aggregated trade event."""
    symbol: str = Field(description="Uppercase trading pair symbol, e.g. BTCUSDT")
    agg_id: int = Field(description="Binance aggregated trade ID ('a') used for sequencing and gap detection")
    price: float = Field(description="Execution price ('p')")
    qty: float = Field(description="Executed base asset quantity ('q')")
    quote_qty: float = Field(description="Executed quote notional value (price * qty)")
    ts: int = Field(description="Execution trade time in millisecond epoch ('T')")
    is_buyer_maker: bool = Field(description="Raw buyer is maker flag ('m')")
    side: Literal["BUY", "SELL"] = Field(
        description="Derived aggressor side: 'SELL' if is_buyer_maker else 'BUY'. "
                    "When m=True, the buyer was maker so the seller crossed the spread (SELL aggressor)."
    )
    first_id: int = Field(description="First trade ID in aggregate bundle ('f')")
    last_id: int = Field(description="Last trade ID in aggregate bundle ('l')")

class BookDelta(BaseModel):
    """Normalized L2 order book diff-depth update event."""
    symbol: str = Field(description="Uppercase trading pair symbol")
    first_update_id: int = Field(description="First update ID in event ('U')")
    final_update_id: int = Field(description="Final update ID in event ('u')")
    bids: list[list[float]] = Field(description="List of [price, qty] bid updates. qty==0 removes level")
    asks: list[list[float]] = Field(description="List of [price, qty] ask updates. qty==0 removes level")
    event_ts: int = Field(description="Binance event timestamp in milliseconds ('E')")

class BookSnapshot(BaseModel):
    """L2 Order book depth snapshot."""
    symbol: str = Field(description="Uppercase trading pair symbol")
    last_update_id: int = Field(description="Last update ID included in snapshot")
    bids: list[list[float]] = Field(description="Top bids as [price, qty]")
    asks: list[list[float]] = Field(description="Top asks as [price, qty]")
    ts: int = Field(description="Snapshot timestamp in milliseconds")
    source: Literal["REST", "PARTIAL_STREAM", "MAINTAINED"] = Field(description="Origin of depth snapshot")

class LadderLevel(BaseModel):
    """Single aggregated price level row in the DOM ladder."""
    price: float = Field(description="Price level rounded to tick group")
    bid_size: float = Field(default=0.0, description="Resting bid size in base units")
    ask_size: float = Field(default=0.0, description="Resting ask size in base units")
    bid_notional: float = Field(default=0.0, description="Resting bid notional in quote units (USD)")
    ask_notional: float = Field(default=0.0, description="Resting ask notional in quote units (USD)")
    is_wall: bool = Field(default=False, description="Flag indicating large resting liquidity wall")
    is_poc: bool = Field(default=False, description="Flag indicating point of control price")
    iceberg_suspected: bool = Field(default=False, description="Flag indicating possible iceberg activity")
    traded_buy: float = Field(default=0.0, description="Recently executed aggressive buy volume at this price")
    traded_sell: float = Field(default=0.0, description="Recently executed aggressive sell volume at this price")
    depth_pct: float = Field(default=0.0, description="Size relative to largest visible level on ladder (0.0 - 1.0)")

class StreamHealth(BaseModel):
    """Operational health metrics for symbol websocket stream."""
    symbol: str = Field(description="Uppercase trading pair symbol")
    connected: bool = Field(description="True if underlying socket connection is active")
    streams: list[str] = Field(default_factory=list, description="List of active stream names subscribed")
    last_trade_ts: int = Field(default=0, description="Epoch ms of latest received trade")
    last_book_ts: int = Field(default=0, description="Epoch ms of latest received book update")
    messages_per_sec: float = Field(default=0.0, description="Inbound message ingestion rate")
    reconnects: int = Field(default=0, description="Cumulative reconnection count")
    book_resyncs: int = Field(default=0, description="Cumulative order book resynchronizations")
    gap_events: int = Field(default=0, description="Detected trade or depth sequence gap events")
    lag_ms: int = Field(default=0, description="Ingestion latency in ms (current_time - event_time)")
    status: Literal["LIVE", "DEGRADED", "DISCONNECTED", "DISABLED"] = Field(
        default="DISCONNECTED",
        description="High level status indicator"
    )
