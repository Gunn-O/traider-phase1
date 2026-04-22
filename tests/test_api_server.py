"""
Unit Tests for API Server

Tests:
- GET /api/status
- POST /api/start
- POST /api/stop
- POST /api/emergency-stop
- GET /api/health
- Helper functions (update_bot_state, add_log)
"""

import pytest
from fastapi.testclient import TestClient

# Import app and bot_state
from api_server import app, bot_state, update_bot_state, add_log, get_bot_status


# ============================================================================
# TEST CLIENT
# ============================================================================

@pytest.fixture
def client():
    """FastAPI test client"""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_bot_state():
    """Reset bot_state before each test"""
    bot_state["status"] = "stopped"
    bot_state["symbol"] = "XAUUSDm"
    bot_state["trading_tf"] = "M5"
    bot_state["current_price"] = 0.0
    bot_state["active_plan_id"] = ""
    bot_state["open_orders"] = []
    bot_state["daily_pnl"] = 0.0
    bot_state["total_pnl"] = 0.0
    bot_state["win"] = 0
    bot_state["loss"] = 0
    bot_state["consecutive_loss"] = 0
    bot_state["last_decision"] = {}
    bot_state["last_reflection"] = "No history yet"
    bot_state["logs"] = []
    bot_state["balance"] = 0.0
    yield


# ============================================================================
# TEST GET /api/status
# ============================================================================

def test_get_status(client):
    """Test GET /api/status returns current bot state"""
    response = client.get("/api/status")

    assert response.status_code == 200
    data = response.json()

    # Check required fields
    assert "status" in data
    assert "trading_tf" in data
    assert "current_price" in data
    assert "balance" in data
    assert "last_updated" in data

    # Check initial values
    assert data["status"] == "stopped"
    assert data["trading_tf"] == "M5"


def test_get_status_with_updates(client):
    """Test GET /api/status reflects bot_state updates"""
    # Update bot_state
    update_bot_state({
        "status": "running",
        "current_price": 3245.50,
        "balance": 500.0
    })

    response = client.get("/api/status")
    data = response.json()

    assert data["status"] == "running"
    assert data["current_price"] == 3245.50
    assert data["balance"] == 500.0


# ============================================================================
# TEST POST /api/start
# ============================================================================

def test_start_bot_success(client):
    """Test POST /api/start successfully starts bot"""
    response = client.post("/api/start", json={"tf": "M5", "symbol": "XAUUSDm"})

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "started"
    assert data["tf"] == "M5"
    assert data["symbol"] == "XAUUSDm"

    # Check bot_state updated
    assert bot_state["status"] == "running"
    assert bot_state["symbol"] == "XAUUSDm"
    assert bot_state["trading_tf"] == "M5"
    assert len(bot_state["logs"]) > 0


def test_start_bot_different_tf(client):
    """Test POST /api/start with different timeframe"""
    response = client.post("/api/start", json={"tf": "H1", "symbol": "XAUUSDm"})

    assert response.status_code == 200
    data = response.json()

    assert data["tf"] == "H1"
    assert bot_state["trading_tf"] == "H1"


def test_start_bot_real_symbol(client):
    """Test POST /api/start with XAUUSD (Real) symbol"""
    response = client.post("/api/start", json={"tf": "M5", "symbol": "XAUUSD"})

    assert response.status_code == 200
    data = response.json()

    assert data["symbol"] == "XAUUSD"
    assert bot_state["symbol"] == "XAUUSD"


def test_start_bot_already_running(client):
    """Test POST /api/start fails if bot already running"""
    # Start bot first
    client.post("/api/start", json={"tf": "M5", "symbol": "XAUUSDm"})

    # Try to start again
    response = client.post("/api/start", json={"tf": "M5", "symbol": "XAUUSDm"})

    assert response.status_code == 400
    assert "already running" in response.json()["detail"].lower()


def test_start_bot_invalid_tf(client):
    """Test POST /api/start fails with invalid timeframe"""
    response = client.post("/api/start", json={"tf": "INVALID", "symbol": "XAUUSDm"})

    assert response.status_code == 400
    assert "invalid tf" in response.json()["detail"].lower()


def test_start_bot_invalid_symbol(client):
    """Test POST /api/start fails with invalid symbol"""
    response = client.post("/api/start", json={"tf": "M5", "symbol": "INVALID"})

    assert response.status_code == 400
    assert "invalid symbol" in response.json()["detail"].lower()


# ============================================================================
# TEST POST /api/stop
# ============================================================================

def test_stop_bot_success(client):
    """Test POST /api/stop successfully stops bot"""
    # Start bot first
    client.post("/api/start", json={"tf": "M5", "symbol": "XAUUSDm"})

    # Stop bot
    response = client.post("/api/stop", json={"reason": "Test stop"})

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "stopped"
    assert data["reason"] == "Test stop"

    # Check bot_state updated
    assert bot_state["status"] == "stopped"


def test_stop_bot_not_running(client):
    """Test POST /api/stop fails if bot not running"""
    response = client.post("/api/stop", json={"reason": "Test"})

    assert response.status_code == 400
    assert "not running" in response.json()["detail"].lower()


# ============================================================================
# TEST POST /api/emergency-stop
# ============================================================================

def test_emergency_stop(client):
    """Test POST /api/emergency-stop"""
    # Setup: Add some open orders
    bot_state["status"] = "running"
    bot_state["open_orders"] = [
        {"trade_id": "TRD-001", "action": "BUY"},
        {"trade_id": "TRD-002", "action": "SELL"}
    ]
    bot_state["active_plan_id"] = "PLAN-001"

    response = client.post("/api/emergency-stop")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "emergency_stopped"
    assert data["orders_closed"] == 2

    # Check bot_state updated
    assert bot_state["status"] == "stopped"
    assert bot_state["open_orders"] == []
    assert bot_state["active_plan_id"] == ""


def test_emergency_stop_no_orders(client):
    """Test POST /api/emergency-stop with no open orders"""
    bot_state["status"] = "running"

    response = client.post("/api/emergency-stop")

    assert response.status_code == 200
    data = response.json()

    assert data["orders_closed"] == 0


# ============================================================================
# TEST GET /api/health
# ============================================================================

def test_health_check(client):
    """Test GET /api/health returns healthy status"""
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "bot_status" in data


# ============================================================================
# TEST GET /api/history
# ============================================================================

def test_get_history(client):
    """Test GET /api/history returns trade history placeholder"""
    response = client.get("/api/history")

    assert response.status_code == 200
    data = response.json()

    assert "trades" in data
    assert "count" in data
    assert isinstance(data["trades"], list)


def test_get_history_with_limit(client):
    """Test GET /api/history with limit parameter"""
    response = client.get("/api/history?limit=10")

    assert response.status_code == 200
    # Currently returns empty list (placeholder)
    assert response.json()["count"] == 0


# ============================================================================
# TEST HELPER FUNCTIONS
# ============================================================================

def test_update_bot_state():
    """Test update_bot_state helper function"""
    update_bot_state({
        "current_price": 3250.75,
        "status": "running",
        "balance": 600.0
    })

    assert bot_state["current_price"] == 3250.75
    assert bot_state["status"] == "running"
    assert bot_state["balance"] == 600.0
    assert "last_updated" in bot_state


def test_update_bot_state_partial():
    """Test update_bot_state with partial updates"""
    initial_balance = bot_state["balance"]

    update_bot_state({"current_price": 3240.00})

    assert bot_state["current_price"] == 3240.00
    assert bot_state["balance"] == initial_balance  # Unchanged


def test_add_log():
    """Test add_log helper function"""
    add_log("Test log message 1")
    add_log("Test log message 2")

    assert len(bot_state["logs"]) == 2
    assert "Test log message 1" in bot_state["logs"][0]
    assert "Test log message 2" in bot_state["logs"][1]


def test_add_log_max_50():
    """Test add_log keeps only last 50 logs"""
    # Add 60 logs
    for i in range(60):
        add_log(f"Log {i}")

    # Should keep only last 50
    assert len(bot_state["logs"]) == 50

    # First log should be "Log 10" (logs 0-9 dropped)
    assert "Log 10" in bot_state["logs"][0]
    assert "Log 59" in bot_state["logs"][-1]


def test_get_bot_status():
    """Test get_bot_status helper function"""
    assert get_bot_status() == "stopped"

    update_bot_state({"status": "running"})
    assert get_bot_status() == "running"

    update_bot_state({"status": "error"})
    assert get_bot_status() == "error"


# ============================================================================
# TEST DASHBOARD SERVING
# ============================================================================

def test_serve_dashboard(client):
    """Test GET / serves dashboard HTML"""
    response = client.get("/")

    # Should return HTML (200) or 404 if dashboard.html not found
    assert response.status_code in [200, 404]

    if response.status_code == 200:
        # Check content type
        assert "text/html" in response.headers.get("content-type", "")


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
