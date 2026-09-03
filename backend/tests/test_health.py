import pytest
from fastapi.testclient import TestClient
from backend.main import fastapi_app

client = TestClient(fastapi_app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "volhelix-ai"
