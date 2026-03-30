from datetime import datetime, timezone

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


def test_backtest_endpoint_passes_signal_filters(monkeypatch):
    app = FastAPI()
    cfg = {
        "pair": "BTCUSDT",
        "min_votes": 3,
        "signal_filters": {
            "min_ema_spread_pct": 0.0005,
            "require_rsi_ema_alignment": True,
            "rsi_ema_alignment_tolerance": 0.002,
            "vwap_crossover_only": True,
            "vwap_vol_threshold": 1.2,
            "breakout_vol_threshold": 1.5,
            "macd_rsi_long_min": 40.0,
            "macd_rsi_long_max": 68.0,
            "macd_rsi_short_min": 32.0,
            "macd_rsi_short_max": 60.0,
            "min_signal_strength": 0.0,
        },
    }
    runtime_state = {"candlesBuffered": {"1m": 100}, "lastFetchLatencyMs": 10, "intervalStatus": {"1m": {"ok": True}}}
    setup_routes(app, cfg, datetime.now(timezone.utc), runtime_state)
    client = TestClient(app)

    async def fake_fetch_candles_paginated(pair, interval, limit):
        times = pd.date_range("2026-01-01", periods=120, freq="min", tz="UTC")
        return pd.DataFrame({
            "time": times,
            "open": [50000.0] * 120,
            "high": [50100.0] * 120,
            "low": [49900.0] * 120,
            "close": [50000.0] * 120,
            "volume": [100.0] * 120,
        })

    captured = {}

    def fake_run_backtest(df, passed_config):
        captured["config"] = passed_config
        return []

    monkeypatch.setattr("scanner.fetcher.fetch_candles_paginated", fake_fetch_candles_paginated)
    monkeypatch.setattr("scanner.backtester.run_backtest", fake_run_backtest)

    payload = {
        "limit": 120,
        "minEmaSpreadPct": 0.001,
        "vwapCrossoverOnly": False,
        "minSignalStrength": 0.4,
    }
    res = client.post("/backtest", json=payload)
    assert res.status_code == 200
    sf = captured["config"]["signal_filters"]
    assert sf["min_ema_spread_pct"] == 0.001
    assert sf["vwap_crossover_only"] is False
    assert sf["min_signal_strength"] == 0.4
