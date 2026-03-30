import pandas as pd

from scanner.strategies import (
    EMAcrossoverStrategy,
    RSIBollingerStrategy,
    VWAPBounceStrategy,
    RangeTradingStrategy,
    BreakoutStrategy,
    MACDMomentumStrategy,
    NeuralNetworkStrategy,
    run_all_strategies,
)


def _range_df(base=100.0):
    return pd.DataFrame({
        "high": [base + 0.5] * 25,
        "low": [base - 0.5] * 25,
    })


def test_ema_strategy_long_short_neutral(snapshot_factory, base_config):
    strat = EMAcrossoverStrategy()
    # Bullish crossover with sufficient EMA spread (ema_fast clearly above ema_slow)
    bullish_snapshot = snapshot_factory(
        ema_crossover="bullish",
        ema_fast=101.0,
        ema_slow=100.0,
        ema_spread_pct=0.001,
    )
    assert strat.evaluate(bullish_snapshot, base_config).direction == "LONG"
    # Bearish crossover with sufficient EMA spread
    assert strat.evaluate(snapshot_factory(ema_crossover="bearish", ema_fast=99.0, ema_slow=100.0, ema_spread_pct=0.001), base_config).direction == "SHORT"
    # No crossover
    assert strat.evaluate(snapshot_factory(ema_crossover="none"), base_config).direction == "NEUTRAL"
    # Bullish crossover but spread too small → whipsaw protection → NEUTRAL
    assert strat.evaluate(snapshot_factory(ema_crossover="bullish", ema_spread_pct=0.00001), base_config).direction == "NEUTRAL"


def test_ema_strategy_respects_configured_min_spread(snapshot_factory, base_config):
    strat = EMAcrossoverStrategy()
    config = dict(base_config)
    config["signal_filters"] = {"min_ema_spread_pct": 0.002}

    # Below configured threshold -> filtered out
    assert strat.evaluate(
        snapshot_factory(ema_crossover="bullish", ema_spread_pct=0.0015),
        config,
    ).direction == "NEUTRAL"

    # Above configured threshold -> allowed
    assert strat.evaluate(
        snapshot_factory(ema_crossover="bullish", ema_spread_pct=0.0025),
        config,
    ).direction == "LONG"


def test_rsi_bollinger_strategy_long_short_neutral(snapshot_factory, base_config):
    strat = RSIBollingerStrategy()
    # LONG: RSI oversold + below BB + EMA aligned (ema_fast >= ema_slow)
    long_snapshot = snapshot_factory(
        rsi=20,
        close_vs_bb="below_lower",
        ema_fast=101.0,
        ema_slow=100.0,
    )
    assert strat.evaluate(long_snapshot, base_config).direction == "LONG"
    # SHORT: RSI overbought + above BB + EMA aligned (ema_fast <= ema_slow)
    short_snapshot = snapshot_factory(
        rsi=80,
        close_vs_bb="above_upper",
        ema_fast=99.0,
        ema_slow=100.0,
    )
    assert strat.evaluate(short_snapshot, base_config).direction == "SHORT"
    # NEUTRAL: mid-RSI
    assert strat.evaluate(snapshot_factory(rsi=50, close_vs_bb="inside"), base_config).direction == "NEUTRAL"
    # LONG condition but bearish EMA alignment → NEUTRAL (trend filter)
    misaligned_snapshot = snapshot_factory(
        rsi=20,
        close_vs_bb="below_lower",
        ema_fast=97.0,
        ema_slow=100.0,
    )
    assert strat.evaluate(misaligned_snapshot, base_config).direction == "NEUTRAL"


def test_vwap_bounce_strategy_long_short_neutral(snapshot_factory, base_config):
    strat = VWAPBounceStrategy()
    # LONG: actual VWAP crossover (prev below, now above) with sufficient volume
    assert strat.evaluate(snapshot_factory(close_vs_vwap="above", prev_close_vs_vwap="below", volume_ratio=1.3), base_config).direction == "LONG"
    # SHORT: actual VWAP crossover (prev above, now below) with sufficient volume
    assert strat.evaluate(snapshot_factory(close_vs_vwap="below", prev_close_vs_vwap="above", volume_ratio=1.3), base_config).direction == "SHORT"
    # NEUTRAL: no crossover (was already above VWAP)
    assert strat.evaluate(snapshot_factory(close_vs_vwap="above", prev_close_vs_vwap="above", volume_ratio=1.3), base_config).direction == "NEUTRAL"
    # NEUTRAL: volume too low
    assert strat.evaluate(snapshot_factory(close_vs_vwap="above", prev_close_vs_vwap="below", volume_ratio=1.0), base_config).direction == "NEUTRAL"


def test_range_strategy_long_short_neutral(snapshot_factory, base_config):
    strat = RangeTradingStrategy()
    df = _range_df(base=100.0)
    assert strat.evaluate(snapshot_factory(current_price=99.55, rsi=40), base_config, df).direction == "LONG"
    assert strat.evaluate(snapshot_factory(current_price=100.45, rsi=60), base_config, df).direction == "SHORT"

    trending_df = pd.DataFrame({
        "high": [100 + i for i in range(25)],
        "low": [90 + i for i in range(25)],
    })
    assert strat.evaluate(snapshot_factory(current_price=120, rsi=50), base_config, trending_df).direction == "NEUTRAL"


def test_breakout_strategy_long_short_neutral(snapshot_factory, base_config):
    strat = BreakoutStrategy()
    df = _range_df(base=100.0)
    assert strat.evaluate(snapshot_factory(current_price=101.0, volume_ratio=2.0), base_config, df).direction == "LONG"
    assert strat.evaluate(snapshot_factory(current_price=99.0, volume_ratio=2.0), base_config, df).direction == "SHORT"
    assert strat.evaluate(snapshot_factory(current_price=100.0, volume_ratio=1.0), base_config, df).direction == "NEUTRAL"


def test_macd_strategy_long_short_neutral(snapshot_factory, base_config):
    strat = MACDMomentumStrategy()
    # LONG: bullish MACD cross + RSI in optimal zone [40–68]
    assert strat.evaluate(snapshot_factory(macd_cross="bullish", macd_histogram=1, close_vs_vwap="above", rsi=55.0), base_config).direction == "LONG"
    # SHORT: bearish MACD cross + RSI in optimal zone [32–60]
    assert strat.evaluate(snapshot_factory(macd_cross="bearish", macd_histogram=-1, close_vs_vwap="below", rsi=45.0), base_config).direction == "SHORT"
    # NEUTRAL: no MACD cross
    assert strat.evaluate(snapshot_factory(macd_cross="none", macd_histogram=0, close_vs_vwap="above"), base_config).direction == "NEUTRAL"
    # NEUTRAL: bullish MACD but RSI overbought (above 68)
    assert strat.evaluate(snapshot_factory(macd_cross="bullish", macd_histogram=1, close_vs_vwap="above", rsi=75.0), base_config).direction == "NEUTRAL"
    # NEUTRAL: bearish MACD but RSI oversold (below 32)
    assert strat.evaluate(snapshot_factory(macd_cross="bearish", macd_histogram=-1, close_vs_vwap="below", rsi=25.0), base_config).direction == "NEUTRAL"


def test_neural_strategy_long_short_neutral(snapshot_factory, base_config):
    strat = NeuralNetworkStrategy()
    neutral_cfg = dict(base_config)
    neutral_cfg["signal_filters"] = {"ml_long_threshold": 0.7, "ml_short_threshold": 0.3}
    assert strat.evaluate(
        snapshot_factory(ema_fast=102, ema_slow=100, macd_histogram=1.2, close_vs_vwap="above", rsi=60, volume_ratio=1.8),
        base_config
    ).direction == "LONG"
    assert strat.evaluate(
        snapshot_factory(ema_fast=98, ema_slow=100, macd_histogram=-1.1, close_vs_vwap="below", rsi=40, volume_ratio=0.8),
        base_config
    ).direction == "SHORT"
    assert strat.evaluate(
        snapshot_factory(ema_fast=100, ema_slow=100, macd_histogram=0.0, close_vs_vwap="above", rsi=50, volume_ratio=1.0),
        neutral_cfg
    ).direction == "NEUTRAL"


def test_run_all_strategies_returns_all_enabled(snapshot_factory, base_config):
    results = run_all_strategies(snapshot_factory(), base_config, _range_df())
    assert len(results) == 7
    assert {r.strategy_name for r in results} == {
        "EMAcrossoverStrategy",
        "RSIBollingerStrategy",
        "VWAPBounceStrategy",
        "RangeTradingStrategy",
        "BreakoutStrategy",
        "MACDMomentumStrategy",
        "NeuralNetworkStrategy",
    }


def test_run_all_strategies_respects_enabled_strategy_selection(snapshot_factory, base_config):
    cfg = dict(base_config)
    cfg["enabled_strategies"] = ["EMAcrossoverStrategy", "NeuralNetworkStrategy"]
    results = run_all_strategies(snapshot_factory(), cfg, _range_df())
    assert {r.strategy_name for r in results} == {"EMAcrossoverStrategy", "NeuralNetworkStrategy"}
