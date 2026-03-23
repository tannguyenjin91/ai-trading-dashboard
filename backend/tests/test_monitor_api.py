# backend/tests/test_monitor_api.py
import pytest
from fastapi.testclient import TestClient
from main import app

@pytest.fixture
def client():
    # Lifespan will run, initializing monitor on app.state
    # We might need to mock some heavy infrastructure if it fails
    with TestClient(app) as c:
        yield c

def test_get_status(client):
    response = client.get("/v1/monitor/status")
    assert response.status_code == 200
    data = response.json()
    assert "is_kill_switch_active" in data
    assert "is_live_trading_enabled" in data
    assert data["is_kill_switch_active"] is False

def test_toggle_kill_switch(client):
    # Enable
    response = client.post("/v1/monitor/kill-switch", json={"active": True})
    assert response.status_code == 200
    
    # Verify status
    response = client.get("/v1/monitor/status")
    assert response.json()["is_kill_switch_active"] is True
    
    # Disable
    client.post("/v1/monitor/kill-switch", json={"active": False})
    response = client.get("/v1/monitor/status")
    assert response.json()["is_kill_switch_active"] is False

def test_toggle_live_trading(client):
    # Enable
    response = client.post("/v1/monitor/toggle-live", json={"active": True})
    assert response.status_code == 200
    
    # Verify status
    response = client.get("/v1/monitor/status")
    assert response.json()["is_live_trading_enabled"] is True
