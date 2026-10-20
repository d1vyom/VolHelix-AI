"""Server-computed order confirmation previews."""
import asyncio
from fastapi import APIRouter
from backend.exchange.execution import preview_order
from backend.exchange.schemas import OrderRequest, OrderPreview
router = APIRouter()

@router.post('/api/market/order/preview', response_model=OrderPreview)
async def preview(request: OrderRequest):
    from backend.api.routes import _get_binance_client, _normalize_symbol
    request = request.model_copy(update={'symbol':_normalize_symbol(request.symbol)})
    return await preview_order(request,client=await asyncio.to_thread(_get_binance_client))
