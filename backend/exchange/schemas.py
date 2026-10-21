"""Validated order contracts shared by API and execution paths."""
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from backend.exchange.models import Market

class OrderRequest(BaseModel):
    """Market-aware testnet submission with finite positive sizing."""
    model_config = ConfigDict(allow_inf_nan=False)
    market: Market = 'spot'
    symbol: str = Field(min_length=1)
    reduce_only: bool = False
    client_order_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{1,36}$')
    qty: float = Field(default=0.001, gt=0)
    side: Literal['BUY', 'SELL'] = 'BUY'
    order_type: Literal['MARKET', 'LIMIT'] = 'MARKET'
    limit_price: float | None = Field(default=None, gt=0)
    quote_quantity: float | None = Field(default=None, gt=0)

    @field_validator('side', 'order_type', mode='before')
    @classmethod
    def uppercase(cls, value: str) -> str:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode='after')
    def limit_requires_price(self) -> 'OrderRequest':
        if self.market == 'futures' and self.quote_quantity is not None:
            raise ValueError('Futures requires base qty, without quote_quantity')
        if self.order_type == 'LIMIT' and (self.limit_price is None or self.quote_quantity is not None):
            raise ValueError('LIMIT requires limit_price and base qty, without quote_quantity')
        return self

class OrderResult(BaseModel):
    """Actual exchange acknowledgement; zero execution is not a fill."""
    order_id: str
    client_order_id: str | None = None
    exchange_status: Literal['NEW', 'PARTIALLY_FILLED', 'FILLED', 'PENDING_NEW']
    executed_qty: float = Field(ge=0, allow_inf_nan=False)
    orig_qty: float = Field(ge=0, allow_inf_nan=False)
    entry_price: float = Field(ge=0, allow_inf_nan=False)
    current_price: float = Field(gt=0, allow_inf_nan=False)


class OrderPreview(BaseModel):
    """Fresh server verdict for confirmation; it is never an execution permit."""
    model_config = ConfigDict(extra='allow')
    approved: bool
    reason: str
    checks: dict[str, bool]
    market: str = 'spot'
    testnet: bool = True
    coverage_started_at: str | None = None
    risk_coverage: str | None = None
