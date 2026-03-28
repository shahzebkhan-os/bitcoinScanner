from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from scanner.indicators import IndicatorSnapshot


@pytest.fixture
def base_config() -> dict:
    return {
        "min_votes": 3,
        "indicators": {
            "ema_fast": 9,
            "ema_slow": 21,
            "rsi_period": 14,
            "rsi_overbought": 70,
            "rsi_oversold": 30,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "bb_period": 20,
            "bb_std": 2,
        },
    }


@pytest.fixture
def candles_df() -> pd.DataFrame:
    times = pd.date_range("2026-01-01", periods=220, freq="min", tz="UTC")
    closes = [100 + (i * 0.1) for i in range(220)]
    return pd.DataFrame({
        "time": times,
        "open": closes,
        "high": [c + 0.5 for c in closes],
        "low": [c - 0.5 for c in closes],
        "close": closes,
        "volume": [1000 + (i * 3) for i in range(220)],
    })


@pytest.fixture
def snapshot_factory():
    def _build(**overrides):
        base = dict(
            ema_fast=101.0,
            ema_slow=100.0,
            ema_crossover="none",
            rsi=50.0,
            macd_line=1.0,
            macd_signal=0.8,
            macd_histogram=0.2,
            macd_cross="none",
            bb_upper=110.0,
            bb_middle=100.0,
            bb_lower=90.0,
            bb_bandwidth=0.2,
            close_vs_bb="inside",
            vwap=100.0,
            close_vs_vwap="above",
            current_volume=1500.0,
            avg_volume=1000.0,
            volume_ratio=1.5,
            current_price=101.0,
            timestamp=datetime.now(timezone.utc),
        )
        base.update(overrides)
        return IndicatorSnapshot(**base)

    return _build
