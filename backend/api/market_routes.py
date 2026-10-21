"""Market discovery, reads and server-computed order confirmation previews."""
import asyncio
from fastapi import APIRouter, HTTPException, Query
from backend.exchange.execution import preview_order
from backend.exchange.schemas import OrderRequest, OrderPreview
from backend.exchange.models import Market
from backend.exchange import registry, catalog
router = APIRouter()

async def _read(market, method, *args, **kwargs):
    def fetch():
        # Legacy Spot list reads use [] on errors; common reads must distinguish
        # an unavailable upstream from a verified empty result.
        params = dict(kwargs, strict=True) if market=='spot' and method in ('get_klines','get_positions') else kwargs
        return getattr(registry.get_exchange_client(market),method)(*args,**params)
    try:
        result = await asyncio.to_thread(fetch)
        if isinstance(result,dict) and result.get('error'):
            raise ValueError(result['error'])
        return result
    except Exception as exc:
        raise HTTPException(status_code=503,detail=f'{market} data unavailable: {exc}') from exc

@router.post('/api/market/order/preview', response_model=OrderPreview)
async def preview(request: OrderRequest):
    from backend.api.routes import _normalize_symbol
    request = request.model_copy(update={'symbol':_normalize_symbol(request.symbol)})
    return await preview_order(request,client=await asyncio.to_thread(registry.get_exchange_client,request.market))

@router.get('/api/market/instruments')
async def instruments(market: Market = 'spot', search: str = Query(default='',max_length=60)):
    try:
        return {'market':market,'instruments':await catalog.list_instruments(market,search)}
    except Exception as exc:
        raise HTTPException(status_code=503,detail='Market catalog unavailable') from exc

@router.get('/api/market/quote')
async def quote(market: Market = 'spot', symbol: str = Query(default='BTCUSDT',pattern=r'^[A-Z0-9]{2,30}$')):
    return {'market':market,**await _read(market,'get_price',symbol)}

@router.get('/api/market/bars')
async def bars(market: Market = 'spot', symbol: str = Query(default='BTCUSDT',pattern=r'^[A-Z0-9]{2,30}$'),
               interval: str = Query(default='1h',pattern=r'^(1m|3m|5m|15m|30m|1h|2h|4h|6h|8h|12h|1d|3d|1w|1M)$'),
               limit: int = Query(default=100,ge=1,le=1000)):
    return {'market':market,'symbol':symbol,'bars':await _read(market,'get_klines',symbol,interval=interval,limit=limit)}

@router.get('/api/market/depth')
async def depth(market: Market = 'spot', symbol: str = Query(default='BTCUSDT',pattern=r'^[A-Z0-9]{2,30}$')):
    return {'market':market,**await _read(market,'get_order_book',symbol,limit=20)}

@router.get('/api/market/account')
async def account(market: Market = 'spot'):
    return {'market':market,'testnet':True,**await _read(market,'get_account')}

@router.get('/api/market/positions')
async def positions(market: Market = 'spot'):
    return {'market':market,'testnet':True,'positions':await _read(market,'get_positions')}
