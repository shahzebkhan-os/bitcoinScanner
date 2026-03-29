from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.rest_routes import setup_routes


def test_config_endpoint_returns_camelcase_and_risk():
    app = FastAPI()
    cfg = {
        "pair": "BTCUSDT",
        "risk": {
            "max_leverage": 5,
            "risk_per_trade_pct": 1.0,
            "target_rr": 1.5,
            "default_stop_loss_pct": 0.002,
        },
        "telegram": {"bot_token": "secret", "chat_id": "x"},
    }
    runtime_state = {"candlesBuffered": {"1m": 100}, "lastFetchLatencyMs": 10, "intervalStatus": {"1m": {"ok": True}}}
    setup_routes(app, cfg, datetime.now(timezone.utc), runtime_state)

    client = TestClient(app)
    data = client.get("/config").json()
    assert "risk" in data
    assert data["risk"]["targetRr"] == 1.5
    assert data["risk"]["defaultStopLossPct"] == 0.002
    assert data["telegram"]["botToken"] == "***REDACTED***"


def test_health_endpoint_returns_structured_metrics():
    app = FastAPI()
    cfg = {"pair": "BTCUSDT"}
    runtime_state = {
        "candlesBuffered": {"1m": 100, "2m": 90, "3m": 80},
        "lastFetchLatencyMs": 15.2,
        "intervalStatus": {"1m": {"ok": True, "message": "Active"}},
    }
    setup_routes(app, cfg, datetime.now(timezone.utc), runtime_state)
    client = TestClient(app)
    health = client.get("/health").json()
    assert "candlesBuffered" in health
    assert "lastFetchLatencyMs" in health
    assert "intervalStatus" in health
