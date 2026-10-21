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

@pytest.mark.parametrize('failure,path',[
    ('candles','/api/market/bars?market=spot&symbol=SOLUSDT'),
    ('account','/api/market/positions?market=spot'),
    ('valuation','/api/market/positions?market=spot'),
])
def test_common_spot_routes_report_actual_sdk_outages(exchange_fixture,monkeypatch,failure,path):
    from fastapi.testclient import TestClient
    from backend.main import fastapi_app
    import backend.api.routes as routes
    monkeypatch.setattr(routes,'_binance_client',exchange_fixture)
    exchange_fixture.market_client.get_all_tickers.side_effect=None
    exchange_fixture.market_client.get_all_tickers.return_value=[]
    if failure=='candles':
        exchange_fixture.market_client.get_klines.side_effect=RuntimeError('candle outage')
    elif failure=='account':
        exchange_fixture.trading_client.get_account.side_effect=RuntimeError('rejected credentials')
    else:
        exchange_fixture.trading_client.get_account.return_value['balances'].append({'asset':'SOL','free':'1','locked':'0'})
        exchange_fixture.market_client.get_all_tickers.side_effect=RuntimeError('valuation outage')
    response=TestClient(fastapi_app).get(path)
    assert response.status_code==503

def test_common_spot_routes_preserve_verified_empty_results(exchange_fixture,monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import fastapi_app
    import backend.api.routes as routes
    monkeypatch.setattr(routes,'_binance_client',exchange_fixture)
    exchange_fixture.trading_client.get_account.return_value={'canTrade':True,'balances':[]}
    exchange_fixture.market_client.get_all_tickers.side_effect=None
    exchange_fixture.market_client.get_all_tickers.return_value=[]
    exchange_fixture.market_client.get_klines.side_effect=None
    exchange_fixture.market_client.get_klines.return_value=[]
    http=TestClient(fastapi_app)
    positions=http.get('/api/market/positions?market=spot')
    bars=http.get('/api/market/bars?market=spot&symbol=SOLUSDT')
    assert positions.status_code==200 and positions.json()['positions']==[]
    assert bars.status_code==200 and bars.json()['bars']==[]

@pytest.mark.parametrize('balances',[[],[{'asset':'USDT','free':'100','locked':'0'}]])
def test_verified_zero_spot_positions_do_not_depend_on_public_prices(exchange_fixture,monkeypatch,balances):
    from fastapi.testclient import TestClient
    from backend.main import fastapi_app
    import backend.api.routes as routes
    monkeypatch.setattr(routes,'_binance_client',exchange_fixture)
    exchange_fixture.trading_client.get_account.return_value={'canTrade':True,'balances':balances}
    exchange_fixture.market_client.get_all_tickers.side_effect=RuntimeError('public prices offline')
    response=TestClient(fastapi_app).get('/api/market/positions?market=spot')
    assert response.status_code==200 and response.json()['positions']==[]
