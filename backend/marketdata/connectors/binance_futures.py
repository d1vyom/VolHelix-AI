"""Unauthenticated production USD-M Futures market data."""
from backend.marketdata.connectors.binance_spot import BinanceSpotConnector


class BinanceFuturesConnector(BinanceSpotConnector):
    """Reuse Binance payload normalization with distinct REST and websocket routes."""

    name = "Binance USD-M Futures"
    rest_base = "https://fapi.binance.com/fapi/v1"

    def stream_groups(self, symbol: str) -> dict[str, list[str]]:
        """Depth and aggregate trades require separate routed connections."""
        sym = symbol.lower()
        return {
            "wss://fstream.binance.com/public": [f"{sym}@depth@100ms"],
            "wss://fstream.binance.com/market": [f"{sym}@aggTrade"],
        }

    def stream_names(self, symbol: str) -> list[str]:
        """Return all streams for health reporting."""
        return [stream for streams in self.stream_groups(symbol).values() for stream in streams]
