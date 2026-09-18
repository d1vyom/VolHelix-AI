import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.main import fastapi_app
from backend.config import settings

client = TestClient(fastapi_app)

@pytest.fixture
def mock_hub_state():
    with patch("backend.api.flow_routes.hub") as mock_hub:
        from backend.marketdata.models import StreamHealth
        from backend.engine.flow_models import FootprintBar, FootprintCell
        
        mock_hub.health.return_value = {"BTCUSDT": StreamHealth(symbol="BTCUSDT", connected=True, streams=["stream1"], status="LIVE")}
        mock_hub.books = {"BTCUSDT": None}
        
        # mock get_state
        class MockBuffers:
            def __init__(self):
                # Fake a footprint bar
                c1 = FootprintCell(price=100.0)
                c1.buy_volume = 10.0
                c1.sell_volume = 5.0
                c1.delta = 5.0
                
                c2 = FootprintCell(price=101.0)
                c2.buy_volume = 0.0
                c2.sell_volume = 20.0
                c2.delta = -20.0
                
                b = FootprintBar(
                    symbol="BTCUSDT",
                    interval="1m",
                    open_time=1000000,
                    close_time=1000059,
                    open=100.0,
                    high=101.0,
                    low=100.0,
                    close=101.0,
                    volume=35.0,
                    delta=-15.0,
                    cells=[c1, c2],
                    tick_group=10.0
                )
                self.bars = {"1m": [b]}
                self.trades = []
                self.tape = []
                
        class MockBook:
            def __init__(self):
                self.tick_size = 0.01
            def get_snapshot(self, limit):
                from backend.marketdata.models import BookSnapshot
                return BookSnapshot(symbol="BTCUSDT", last_update_id=1, bids=[], asks=[], ts=1000, source="MAINTAINED")
                
        mock_hub.get_state.return_value = {
            "book": MockBook(),
            "buffers": MockBuffers(),
            "health": None
        }
        
        yield mock_hub

def test_flow_status_happy(mock_hub_state):
    settings.FLOW_ENABLED = True
    response = client.get("/api/flow/status")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert "BTCUSDT" in data["symbols"]
    assert "BTCUSDT" in data["health"]

def test_flow_status_disabled():
    settings.FLOW_ENABLED = False
    response = client.get("/api/flow/status")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False

def test_footprint_happy(mock_hub_state):
    settings.FLOW_ENABLED = True
    response = client.get("/api/flow/footprint?symbol=BTCUSDT&interval=1m&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "BTCUSDT"
    assert len(data["bars"]) == 1
    
    bar = data["bars"][0]
    cell_delta_sum = sum(c["delta"] for c in bar["cells"])
    assert bar["delta"] == cell_delta_sum

def test_unknown_symbol_graceful(mock_hub_state):
    settings.FLOW_ENABLED = True
    mock_hub_state.get_state.return_value = None
    response = client.get("/api/flow/footprint?symbol=UNKNOWN")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["error"] == "Symbol not subscribed"

def test_endpoint_disabled():
    settings.FLOW_ENABLED = False
    response = client.get("/api/flow/footprint?symbol=BTCUSDT")
    assert response.status_code == 503
    data = response.json()
    assert data["detail"]["enabled"] is False
