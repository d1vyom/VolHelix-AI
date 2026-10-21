from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from backend.marketdata.models import StreamHealth
from backend.engine.flow_models import FootprintBar, TapeEntry, HeatmapSnapshot, VolumeProfileSnapshot, CVDPoint, FlowMetrics, DomAnalytics

class StatusResponse(BaseModel):
    market: Literal["spot", "futures"] = "spot"
    enabled: bool
    symbols: List[str] = []
    health: dict[str, StreamHealth] = {}
    reason: Optional[str] = None

class FootprintResponse(BaseModel):
    symbol: str
    interval: str
    tick_group: float
    bars: List[FootprintBar]

class TapeResponse(BaseModel):
    symbol: str
    entries: List[TapeEntry]

class CVDSnapshotResponse(BaseModel):
    symbol: str
    points: List[CVDPoint]
    vwap: float
    bands: dict[str, float]

class SubscribeRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=30, pattern=r"^[A-Za-z0-9]+$")
    market: Literal["spot", "futures"] = "spot"

class SubscribeResponse(BaseModel):
    success: bool
    symbol: str
    status: str
    error: Optional[str] = None

class UnsubscribeRequest(SubscribeRequest):
    pass

class UnsubscribeResponse(BaseModel):
    success: bool
    symbol: str
    error: Optional[str] = None

class SymbolInfoResponse(BaseModel):
    tick_size: float
    step_size: float
    min_notional: float
    price_precision: int
    qty_precision: int
    default_tick_group: float
