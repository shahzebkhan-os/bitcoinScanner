from datetime import datetime, timezone
import sys
import types

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pandas as pd

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


def _mock_fetcher(monkeypatch, rows: int = 1200):
    times = pd.date_range("2026-01-01", periods=rows, freq="min", tz="UTC")
    closes = [10000 + (i * 0.1) + (((i % 50) - 25) * 2) for i in range(rows)]
    df = pd.DataFrame({
        "time": times,
        "open": closes,
        "high": [c + 5 for c in closes],
        "low": [c - 5 for c in closes],
        "close": closes,
        "volume": [1000 + ((i % 20) * 5) for i in range(rows)],
    })

    async def _fetch_candles_paginated(pair: str, interval: str, limit: int):
        return df.head(limit).copy()

    fetcher_module = types.SimpleNamespace(fetch_candles_paginated=_fetch_candles_paginated, CandleBuffer=object)
    monkeypatch.setitem(sys.modules, "scanner.fetcher", fetcher_module)


def test_grid_search_endpoint_returns_ranked_results(monkeypatch):
    _mock_fetcher(monkeypatch, rows=800)
    app = FastAPI()
    cfg = {"pair": "BTCUSDT", "min_votes": 3, "indicators": {"ema_fast": 9, "ema_slow": 21}}
    setup_routes(app, cfg, datetime.now(timezone.utc), {})
    client = TestClient(app)

    response = client.post("/backtest/grid-search", json={
        "pair": "BTCUSDT",
        "interval": "1m",
        "limit": 600,
        "topN": 3,
        "maxRuns": 10,
        "parameterGrid": {
            "minVotes": [2, 3],
            "emaFast": [8, 9],
        },
    })
    data = response.json()
    assert response.status_code == 200
    assert data["evaluated"] == 4
    assert len(data["results"]) == 3
    assert data["results"][0]["score"] >= data["results"][1]["score"]


def test_walk_forward_endpoint_returns_windows(monkeypatch):
    _mock_fetcher(monkeypatch, rows=1400)
    app = FastAPI()
    cfg = {"pair": "BTCUSDT", "min_votes": 3}
    setup_routes(app, cfg, datetime.now(timezone.utc), {})
    client = TestClient(app)

    response = client.post("/backtest/walk-forward", json={
        "pair": "BTCUSDT",
        "interval": "1m",
        "limit": 1200,
        "trainSize": 300,
        "testSize": 120,
        "stepSize": 120,
        "maxWindows": 4,
    })
    data = response.json()
    assert response.status_code == 200
    assert len(data["windows"]) >= 1
    assert data["summary"]["windowsEvaluated"] == len(data["windows"])
    assert "avgOutOfSampleFinalCapital" in data["summary"]


def test_monte_carlo_endpoint_returns_summary(monkeypatch):
    _mock_fetcher(monkeypatch, rows=900)
    app = FastAPI()
    cfg = {"pair": "BTCUSDT", "min_votes": 2}
    setup_routes(app, cfg, datetime.now(timezone.utc), {})
    client = TestClient(app)

    response = client.post("/backtest/monte-carlo", json={
        "pair": "BTCUSDT",
        "interval": "1m",
        "limit": 800,
        "iterations": 20,
        "seed": 123,
    })
    data = response.json()
    assert response.status_code == 200
    assert data["summary"]["iterations"] == 20
    assert data["summary"]["p5FinalCapital"] <= data["summary"]["p95FinalCapital"]


def test_custom_strategy_endpoint_returns_selected_strategies(monkeypatch):
    _mock_fetcher(monkeypatch, rows=700)
    app = FastAPI()
    cfg = {"pair": "BTCUSDT", "min_votes": 3}
    setup_routes(app, cfg, datetime.now(timezone.utc), {})
    client = TestClient(app)

    selected = ["EMAcrossoverStrategy", "MACDMomentumStrategy", "VWAPBounceStrategy"]
    response = client.post("/backtest/custom-strategy", json={
        "pair": "BTCUSDT",
        "interval": "1m",
        "limit": 650,
        "selectedStrategies": selected,
        "customMinVotes": 1,
        "customMinExitVotes": 1,
    })
    data = response.json()
    assert response.status_code == 200
    assert data["selectedStrategies"] == selected
    assert "stats" in data
