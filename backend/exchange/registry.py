"""Resolve explicit market identity; missing Futures setup never falls back."""
from functools import lru_cache
from backend.exchange.models import Market

@lru_cache(maxsize=1)
def _get_futures_client():
    from backend.exchange.futures_client import FuturesClient
    return FuturesClient()

def get_exchange_client(market: Market = 'spot'):
    if market == 'spot':
        from backend.api.routes import _get_binance_client
        return _get_binance_client()
    if market == 'futures':
        return _get_futures_client()
    raise ValueError('Unsupported market')
