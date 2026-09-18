from typing import Protocol, Any
from backend.marketdata.models import Trade, BookDelta, BookSnapshot

class ExchangeConnector(Protocol):
    """Protocol for exchange connectors (future multi-exchange support)."""
    name: str

    def normalize_symbol(self, symbol: str) -> str:
        ...

    def stream_names(self, symbol: str) -> list[str]:
        ...

    def parse(self, raw: dict[str, Any]) -> Trade | BookDelta | Any:
        ...

    async def depth_snapshot(self, symbol: str, limit: int = 1000) -> BookSnapshot:
        ...

    async def tick_size(self, symbol: str) -> float:
        ...
