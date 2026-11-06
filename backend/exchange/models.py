"""Market identity shared by discovery and execution."""
from typing import Literal
from pydantic import BaseModel

Market = Literal['spot', 'futures']

class Instrument(BaseModel):
    market: Market
    symbol: str
    base_asset: str
    quote_asset: str
    contract_type: str | None = None

def normalize_symbol_info(info):
    if not info:
        raise ValueError('Symbol unavailable on testnet')
    return {'symbol': info['symbol'], 'base_asset': info['baseAsset'],
            'quote_asset': info['quoteAsset'], 'status': info['status'],
            'filters': info.get('filters', []), 'contract_type': info.get('contractType'),
            'margin_asset': info.get('marginAsset')}


def execution_price_tick(info):
    """Use exchange PRICE_FILTER metadata, never a price-magnitude guess."""
    from decimal import Decimal
    for rule in info.get('filters', []):
        if rule.get('filterType') == 'PRICE_FILTER':
            tick = Decimal(str(rule.get('tickSize', 0)))
            if tick.is_finite() and tick > 0:
                return str(tick)
    raise ValueError('Verified exchange price tick unavailable')
