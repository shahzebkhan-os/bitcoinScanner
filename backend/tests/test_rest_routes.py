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
        "enabledStrategies": ["EMAcrossoverStrategy", "NeuralNetworkStrategy"],
        "mlLongThreshold": 0.7,
        "mlShortThreshold": 0.3,
        "mlWeightEmaBias": 0.75,
        "mlWeightMacdSign": 0.65,
        "mlWeightVwapBias": 0.55,
        "mlWeightRsiNorm": 0.45,
        "mlWeightVolumeBias": 0.35,
    }
    res = client.post("/backtest", json=payload)
    assert res.status_code == 200
    sf = captured["config"]["signal_filters"]
    assert sf["min_ema_spread_pct"] == 0.001
    assert sf["vwap_crossover_only"] is False
    assert sf["min_signal_strength"] == 0.4
    assert sf["ml_long_threshold"] == 0.7
    assert sf["ml_short_threshold"] == 0.3
    assert sf["ml_weight_ema_bias"] == 0.75
    assert sf["ml_weight_macd_sign"] == 0.65
    assert sf["ml_weight_vwap_bias"] == 0.55
    assert sf["ml_weight_rsi_norm"] == 0.45
    assert sf["ml_weight_volume_bias"] == 0.35
    assert captured["config"]["enabled_strategies"] == ["EMAcrossoverStrategy", "NeuralNetworkStrategy"]


def test_backtest_sweep_ranks_configs(monkeypatch):
    app = FastAPI()
    cfg = {"pair": "BTCUSDT", "min_votes": 3}
    runtime_state = {"candlesBuffered": {"1m": 100}, "lastFetchLatencyMs": 10, "intervalStatus": {"1m": {"ok": True}}}
    setup_routes(app, cfg, datetime.now(timezone.utc), runtime_state)
    client = TestClient(app)

    async def fake_fetch_candles_paginated(pair, interval, limit):
        times = pd.date_range("2026-01-01", periods=150, freq="min", tz="UTC")
        return pd.DataFrame({
            "time": times,
            "open": [50000.0] * 150,
            "high": [50100.0] * 150,
            "low": [49900.0] * 150,
            "close": [50000.0] * 150,
            "volume": [100.0] * 150,
        })

    def fake_run_backtest(df, passed_config):
        # better metrics for minVotes=4 than minVotes=3
        if passed_config.get("min_votes") == 4:
            return [
                {"entry": 100.0, "exitPrice": 110.0, "direction": "LONG", "exitType": "signal"},
                {"entry": 100.0, "exitPrice": 112.0, "direction": "LONG", "exitType": "signal"},
            ]
        return [
            {"entry": 100.0, "exitPrice": 104.0, "direction": "LONG", "exitType": "signal"},
            {"entry": 100.0, "exitPrice": 98.0, "direction": "LONG", "exitType": "signal"},
        ]

    monkeypatch.setattr("scanner.fetcher.fetch_candles_paginated", fake_fetch_candles_paginated)
    monkeypatch.setattr("api.rest_routes.run_backtest", fake_run_backtest)

    payload = {
        "limit": 150,
        "topN": 2,
        "sweep": {
            "minVotes": [3, 4],
            "vwapCrossoverOnly": [True],
        },
    }
    res = client.post("/backtest/sweep", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["totalConfigs"] == 2
    assert data["evaluatedConfigs"] == 2
    assert len(data["results"]) == 2
    assert data["results"][0]["params"]["minVotes"] == 4
    assert "rankScore" in data["results"][0]
    assert "sortinoRatio" in data["results"][0]


def test_backtest_sweep_requires_sweep_object():
    app = FastAPI()
    cfg = {"pair": "BTCUSDT", "min_votes": 3}
    runtime_state = {"candlesBuffered": {"1m": 100}, "lastFetchLatencyMs": 10, "intervalStatus": {"1m": {"ok": True}}}
    setup_routes(app, cfg, datetime.now(timezone.utc), runtime_state)
    client = TestClient(app)

    res = client.post("/backtest/sweep", json={"limit": 100})
    assert res.status_code == 400


def test_backtest_sweep_rejects_excessive_combinations():
    app = FastAPI()
    cfg = {"pair": "BTCUSDT", "min_votes": 3}
    runtime_state = {"candlesBuffered": {"1m": 100}, "lastFetchLatencyMs": 10, "intervalStatus": {"1m": {"ok": True}}}
    setup_routes(app, cfg, datetime.now(timezone.utc), runtime_state)
    client = TestClient(app)

    res = client.post(
        "/backtest/sweep",
        json={
            "maxCombinations": 2,
            "sweep": {
                "minVotes": [2, 3, 4],
            },
        },
    )
    assert res.status_code == 400
