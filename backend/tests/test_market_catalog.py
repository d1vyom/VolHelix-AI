import asyncio
from unittest.mock import Mock
import pytest

def test_catalog_filters_searches_and_expires(monkeypatch):
    from backend.exchange import catalog
    from backend.exchange.models import Instrument
    clock = [10]
    monkeypatch.setattr(catalog.time, 'monotonic', lambda: clock[0])
    catalog._cache.clear()
    data = {'symbols': [
        {'symbol':'SOLUSDT','baseAsset':'SOL','quoteAsset':'USDT','status':'TRADING','isSpotTradingAllowed':True,'contractType':'PERPETUAL'},
        {'symbol':'OLDUSDT','baseAsset':'OLD','quoteAsset':'USDT','status':'BREAK','contractType':'PERPETUAL'},
        {'symbol':'SOLETH','baseAsset':'SOL','quoteAsset':'ETH','status':'TRADING','contractType':'PERPETUAL'},
        {'symbol':'SOLDELUSDT','baseAsset':'SOL','quoteAsset':'USDT','status':'TRADING','isSpotTradingAllowed':False,'contractType':'CURRENT_QUARTER'},
    ]}
    fetch = Mock(return_value=data)
    monkeypatch.setattr(catalog, '_fetch_metadata', fetch)
    for market in ('spot','futures'):
        result = asyncio.run(catalog.list_instruments(market, 'sol'))
        assert [i.symbol for i in result] == ['SOLUSDT']
        assert isinstance(result[0], Instrument)
        asyncio.run(catalog.list_instruments(market, 'unmatched'))
    assert fetch.call_count == 2
    clock[0] += 301
    asyncio.run(catalog.list_instruments('spot'))
    assert fetch.call_count == 3
    assert len(catalog._cache) == 2

def test_catalog_failure_is_not_empty_success(monkeypatch):
    from backend.exchange import catalog
    catalog._cache.clear()
    monkeypatch.setattr(catalog, '_fetch_metadata', Mock(side_effect=RuntimeError('upstream down')))
    with pytest.raises(RuntimeError, match='upstream down'):
        asyncio.run(catalog.list_instruments('futures'))

def test_instrument_route_reports_errors_and_invalid_market(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import fastapi_app
    from backend.exchange import catalog
    catalog._cache.clear()
    monkeypatch.setattr(catalog, '_fetch_metadata', Mock(side_effect=RuntimeError('down')))
    http = TestClient(fastapi_app)
    assert http.get('/api/market/instruments?market=futures').status_code == 503
    assert http.get('/api/market/instruments?market=unknown').status_code == 422
