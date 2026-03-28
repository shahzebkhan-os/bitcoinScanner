from datetime import datetime

from scanner.indicators import IndicatorSnapshot
from scanner.strategies import run_all_strategies


def _snapshot(**overrides):
    base = dict(
        ema_fast=100.0,
        ema_slow=99.0,
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
        vwap=99.5,
        close_vs_vwap="above",
        current_volume=1000.0,
        avg_volume=800.0,
        volume_ratio=1.25,
        current_price=100.0,
        timestamp=datetime.utcnow(),
    )
    base.update(overrides)
    return IndicatorSnapshot(**base)


def test_run_all_strategies_always_returns_6_votes():
    config = {"indicators": {"rsi_oversold": 30, "rsi_overbought": 70}}
    snapshot = _snapshot()
    results = run_all_strategies(snapshot, config, None)
    assert len(results) == 6
    strategy_names = {result.strategy_name for result in results}
    assert strategy_names == {
        "EMAcrossoverStrategy",
        "RSIBollingerStrategy",
        "VWAPBounceStrategy",
        "RangeTradingStrategy",
        "BreakoutStrategy",
        "MACDMomentumStrategy",
    }
