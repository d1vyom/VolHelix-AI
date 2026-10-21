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
