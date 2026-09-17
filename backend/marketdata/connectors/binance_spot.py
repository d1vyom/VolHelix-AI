import httpx
from typing import Any
from backend.marketdata.connectors.base import ExchangeConnector
from backend.marketdata.models import Trade, BookDelta, BookSnapshot
from backend.marketdata.normalizer import (
    normalize_agg_trade,
    normalize_depth_update,
    normalize_depth_snapshot
)
from backend.config import settings

class BinanceSpotConnector:
    """Binance Spot implementation of ExchangeConnector."""
    name: str = "Binance Spot"

    def normalize_symbol(self, symbol: str) -> str:
        return symbol.upper()

    def stream_names(self, symbol: str) -> list[str]:
        sym = symbol.lower()
        return [
            f"{sym}@aggTrade",
            f"{sym}@depth@100ms",
            f"{sym}@depth20@100ms",
            f"{sym}@kline_1m"
        ]

    def parse(self, raw: dict[str, Any]) -> Trade | BookDelta | Any:
        """Parse raw stream payload based on stream name or event type."""
        data = raw.get("data", raw)
        stream = raw.get("stream", "")
        event_type = data.get("e", "")

        if event_type == "aggTrade" or "@aggTrade" in stream:
            return normalize_agg_trade(raw)
        elif event_type == "depthUpdate" or "@depth@100ms" in stream:
            return normalize_depth_update(raw)
        elif event_type == "kline" or "kline" in stream:
            # We don't have a kline normalizer, just return the raw kline data dict
            # The engine will need to access k.t, k.x etc.
            return data
        
        # fallback for @depth20
        if "lastUpdateId" in data and "bids" in data:
            return data

        return data

    async def depth_snapshot(self, symbol: str, limit: int = 1000) -> BookSnapshot:
        """Fetch REST depth snapshot asynchronously."""
        url = "https://api.binance.com/api/v3/depth"
        # We use the public URL for market data as per instructions (not testnet)
        params = {"symbol": symbol.upper(), "limit": limit}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=10.0)
            if resp.status_code == 429 or resp.status_code == 418:
                resp.raise_for_status() # Let it bubble up as HTTPStatusError
            resp.raise_for_status()
            data = resp.json()
            return normalize_depth_snapshot(data, symbol, source="REST")

    async def tick_size(self, symbol: str) -> float:
        """Fetch tick size from exchangeInfo."""
        url = "https://api.binance.com/api/v3/exchangeInfo"
        params = {"symbol": symbol.upper()}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            for s in data.get("symbols", []):
                if s["symbol"] == symbol.upper():
                    for f in s.get("filters", []):
                        if f["filterType"] == "PRICE_FILTER":
                            return float(f["tickSize"])
            raise ValueError(f"PRICE_FILTER not found for {symbol}")

