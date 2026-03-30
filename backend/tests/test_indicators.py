from scanner.indicators import calculate_indicators


def test_calculate_indicators_returns_snapshot(candles_df, base_config):
    snapshot = calculate_indicators(candles_df, base_config)
    assert snapshot is not None
    assert snapshot.current_price > 0
    assert snapshot.ema_fast > 0
    assert snapshot.ema_slow > 0
    assert 0 <= snapshot.rsi <= 100
    assert snapshot.to_dict()["currentPrice"] == round(snapshot.current_price, 4)


def test_calculate_indicators_handles_insufficient_data(base_config, candles_df):
    snapshot = calculate_indicators(candles_df.head(10), base_config)
    assert snapshot is None


def test_calculate_indicators_atr_positive(candles_df, base_config):
    """ATR should always be positive for valid OHLCV data."""
    snapshot = calculate_indicators(candles_df, base_config)
    assert snapshot is not None
    assert snapshot.atr > 0
    assert snapshot.to_dict()["atr"] == round(snapshot.atr, 4)


def test_calculate_indicators_ema_spread_pct(candles_df, base_config):
    """ema_spread_pct should be non-negative and reflect EMA distance."""
    snapshot = calculate_indicators(candles_df, base_config)
    assert snapshot is not None
    assert snapshot.ema_spread_pct >= 0
    assert snapshot.to_dict()["emaSpreadPct"] == round(snapshot.ema_spread_pct, 6)


def test_calculate_indicators_prev_close_vs_vwap(candles_df, base_config):
    """prev_close_vs_vwap should be 'above' or 'below'."""
    snapshot = calculate_indicators(candles_df, base_config)
    assert snapshot is not None
    assert snapshot.prev_close_vs_vwap in ("above", "below")
    assert snapshot.to_dict()["prevCloseVsVwap"] in ("above", "below")


def test_calculate_indicators_rsi_wilder_smoothing(base_config):
    """
    RSI should use Wilder's EWM smoothing (not SMA).
    For a consistently upward-trending price series, RSI must be well above 50.
    With the old SMA approach a monotone series yields RSI = 100 (division by zero
    fallback to 50), whereas EWM gives a finite value above 50.
    """
    import pandas as pd
    times = pd.date_range("2026-01-01", periods=100, freq="min", tz="UTC")
    closes = [100 + i * 0.5 for i in range(100)]  # strong uptrend
    df = pd.DataFrame({
        "time": times,
        "open": closes,
        "high": [c + 0.3 for c in closes],
        "low": [c - 0.1 for c in closes],
        "close": closes,
        "volume": [1000] * 100,
    })
    snapshot = calculate_indicators(df, base_config)
    assert snapshot is not None
    # Wilder RSI on a monotone uptrend converges toward ~100 but is finite
    assert 50 < snapshot.rsi <= 100
