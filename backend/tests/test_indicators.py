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
