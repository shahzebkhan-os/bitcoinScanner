from datetime import datetime, timedelta, timezone

import pandas as pd

from scanner.backtester import run_custom_strategy_backtest


def _candles(rows: int = 240) -> pd.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    times = [start + timedelta(minutes=i) for i in range(rows)]
    closes = [10000 + (i * 0.2) + (((i % 30) - 15) * 1.5) for i in range(rows)]
    return pd.DataFrame({
        "time": times,
        "open": closes,
        "high": [c + 5 for c in closes],
        "low": [c - 5 for c in closes],
        "close": closes,
        "volume": [1000 + (i % 10) * 20 for i in range(rows)],
    })


def test_custom_strategy_backtest_returns_signals_for_valid_selection():
    df = _candles(260)
    config = {"min_votes": 3, "indicators": {"ema_fast": 9, "ema_slow": 21}}
    signals = run_custom_strategy_backtest(
        df=df,
        config=config,
        selected_strategies=["EMAcrossoverStrategy", "MACDMomentumStrategy", "VWAPBounceStrategy"],
        min_votes=1,
        min_exit_votes=1,
    )
    assert isinstance(signals, list)
    assert len(signals) > 0
    assert signals[0]["votes"].endswith("/3")


def test_custom_strategy_backtest_handles_empty_or_invalid_selection():
    df = _candles(260)
    config = {"min_votes": 3, "indicators": {"ema_fast": 9, "ema_slow": 21}}
    assert run_custom_strategy_backtest(df, config, selected_strategies=[], min_votes=1) == []
    assert run_custom_strategy_backtest(
        df, config, selected_strategies=["UnknownStrategy"], min_votes=1
    ) == []
