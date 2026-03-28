import pandas as pd

from scanner.strategies import (
    EMAcrossoverStrategy,
    RSIBollingerStrategy,
    VWAPBounceStrategy,
    RangeTradingStrategy,
    BreakoutStrategy,
    MACDMomentumStrategy,
    run_all_strategies,
)


def _range_df(base=100.0):
    return pd.DataFrame({
        "high": [base + 0.5] * 25,
        "low": [base - 0.5] * 25,
    })


def test_ema_strategy_long_short_neutral(snapshot_factory, base_config):
    strat = EMAcrossoverStrategy()
    assert strat.evaluate(snapshot_factory(ema_crossover="bullish"), base_config).direction == "LONG"
    assert strat.evaluate(snapshot_factory(ema_crossover="bearish"), base_config).direction == "SHORT"
    assert strat.evaluate(snapshot_factory(ema_crossover="none"), base_config).direction == "NEUTRAL"


def test_rsi_bollinger_strategy_long_short_neutral(snapshot_factory, base_config):
    strat = RSIBollingerStrategy()
    assert strat.evaluate(snapshot_factory(rsi=20, close_vs_bb="below_lower"), base_config).direction == "LONG"
    assert strat.evaluate(snapshot_factory(rsi=80, close_vs_bb="above_upper"), base_config).direction == "SHORT"
    assert strat.evaluate(snapshot_factory(rsi=50, close_vs_bb="inside"), base_config).direction == "NEUTRAL"


def test_vwap_bounce_strategy_long_short_neutral(snapshot_factory, base_config):
    strat = VWAPBounceStrategy()
    assert strat.evaluate(snapshot_factory(close_vs_vwap="above", volume_ratio=1.3), base_config).direction == "LONG"
    assert strat.evaluate(snapshot_factory(close_vs_vwap="below", volume_ratio=1.3), base_config).direction == "SHORT"
    assert strat.evaluate(snapshot_factory(close_vs_vwap="above", volume_ratio=1.0), base_config).direction == "NEUTRAL"


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
    assert strat.evaluate(snapshot_factory(macd_cross="bullish", macd_histogram=1, close_vs_vwap="above"), base_config).direction == "LONG"
    assert strat.evaluate(snapshot_factory(macd_cross="bearish", macd_histogram=-1, close_vs_vwap="below"), base_config).direction == "SHORT"
    assert strat.evaluate(snapshot_factory(macd_cross="none", macd_histogram=0, close_vs_vwap="above"), base_config).direction == "NEUTRAL"


def test_run_all_strategies_returns_all_six(snapshot_factory, base_config):
    results = run_all_strategies(snapshot_factory(), base_config, _range_df())
    assert len(results) == 6
    assert {r.strategy_name for r in results} == {
        "EMAcrossoverStrategy",
        "RSIBollingerStrategy",
        "VWAPBounceStrategy",
        "RangeTradingStrategy",
        "BreakoutStrategy",
        "MACDMomentumStrategy",
    }
