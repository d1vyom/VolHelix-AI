"""Public production discovery; two bounded metadata entries, five minute TTL."""
import asyncio
import time
import requests
from backend.exchange.models import Market, Instrument

_cache = {}
TTL_SECONDS = 300

def _fetch_metadata(market):
    url = ('https://api.binance.com/api/v3/exchangeInfo' if market == 'spot'
           else 'https://fapi.binance.com/fapi/v1/exchangeInfo')
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()

async def list_instruments(market: Market = 'spot', search: str = '') -> list[Instrument]:
    if market not in ('spot', 'futures'):
        raise ValueError('Unsupported market')
    cached = _cache.get(market)
    if cached is None or time.monotonic() - cached[0] >= TTL_SECONDS:
        metadata = await asyncio.to_thread(_fetch_metadata, market)
        rows = metadata['symbols']
        instruments = [Instrument(market=market,symbol=s['symbol'],base_asset=s['baseAsset'],
                                  quote_asset=s['quoteAsset'],contract_type=s.get('contractType'))
                       for s in rows if s['status'] == 'TRADING' and s['quoteAsset'] == 'USDT'
                       and (s.get('isSpotTradingAllowed', True) if market == 'spot'
                            else s.get('contractType') == 'PERPETUAL' and s.get('marginAsset', 'USDT') == 'USDT')]
        cached = (time.monotonic(), tuple(sorted(instruments,key=lambda i:i.symbol)))
        _cache[market] = cached
    query = search.strip().upper()
    return [i.model_copy() for i in cached[1] if any(query in v for v in (i.symbol,i.base_asset,i.quote_asset))]
