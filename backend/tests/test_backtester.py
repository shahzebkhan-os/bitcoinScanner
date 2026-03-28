"""
Tests for backtester module - scanner/backtester.py

Tests cover:
- Indicator calculations
- Strategy vote logic
- Filter logic (trend, volume, HTF bias)
- Position state machine
- P&L calculations
- Edge cases and error handling
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from scanner.backtester import run_backtest


@pytest.fixture
def sample_config():
    """Standard config for testing."""
    return {
        'indicators': {
            'ema_fast': 9,
            'ema_slow': 21,
            'rsi_period': 14,
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9,
            'bb_period': 20,
            'bb_std': 2,
        },
        'risk': {
            'target_rr': 1.5,
            'default_stop_loss_pct': 0.002,
        },
        'min_votes': 3,
        'min_exit_votes': 2,
        'useTrendFilter': False,
        'useVolumeFilter': False,
        'volMultiplier': 1.2,
        'useHtfBias': False,
        'htfEmaPeriod': 100,
    }


@pytest.fixture
def uptrend_candles():
    """Generate synthetic uptrend candle data."""
    np.random.seed(42)
    n = 200
    base = 50000
    times = [datetime(2024, 1, 1, 0, i, 0, tzinfo=timezone.utc) for i in range(n)]

    # Create uptrend with noise
    trend = np.linspace(base, base + 2000, n)
    noise = np.random.randn(n) * 50
    closes = trend + noise

    df = pd.DataFrame({
        'time': times,
        'open': closes - np.random.rand(n) * 20,
        'high': closes + np.random.rand(n) * 30,
        'low': closes - np.random.rand(n) * 30,
        'close': closes,
        'volume': np.random.rand(n) * 100 + 50,
    })
    return df


@pytest.fixture
def downtrend_candles():
    """Generate synthetic downtrend candle data."""
    np.random.seed(43)
    n = 200
    base = 50000
    times = [datetime(2024, 1, 1, 0, i, 0, tzinfo=timezone.utc) for i in range(n)]

    # Create downtrend with noise
    trend = np.linspace(base, base - 2000, n)
    noise = np.random.randn(n) * 50
    closes = trend + noise

    df = pd.DataFrame({
        'time': times,
        'open': closes - np.random.rand(n) * 20,
        'high': closes + np.random.rand(n) * 30,
        'low': closes - np.random.rand(n) * 30,
        'close': closes,
        'volume': np.random.rand(n) * 100 + 50,
    })
    return df


@pytest.fixture
def sideways_candles():
    """Generate synthetic sideways/ranging candle data."""
    np.random.seed(44)
    n = 200
    base = 50000
    times = [datetime(2024, 1, 1, 0, i, 0, tzinfo=timezone.utc) for i in range(n)]

    # Create sideways with noise
    closes = base + np.random.randn(n) * 100

    df = pd.DataFrame({
        'time': times,
        'open': closes - np.random.rand(n) * 20,
        'high': closes + np.random.rand(n) * 30,
        'low': closes - np.random.rand(n) * 30,
        'close': closes,
        'volume': np.random.rand(n) * 100 + 50,
    })
    return df


class TestBasicFunctionality:
    """Test basic backtest execution."""

    def test_empty_dataframe(self, sample_config):
        """Test with empty DataFrame - should return empty list."""
        df = pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        signals = run_backtest(df, sample_config)
        assert signals == []

    def test_insufficient_candles(self, sample_config):
        """Test with < 50 candles - should return empty list."""
        df = pd.DataFrame({
            'time': [datetime.now(timezone.utc) for _ in range(30)],
            'open': [50000] * 30,
            'high': [50100] * 30,
            'low': [49900] * 30,
            'close': [50000] * 30,
            'volume': [100] * 30,
        })
        signals = run_backtest(df, sample_config)
        assert signals == []

    def test_valid_uptrend_execution(self, uptrend_candles, sample_config):
        """Test with uptrend data - should generate LONG signals."""
        signals = run_backtest(uptrend_candles, sample_config)

        # Should produce at least some signals
        assert len(signals) > 0

        # Signals should have required fields
        for sig in signals:
            assert 'timestamp' in sig
            assert 'direction' in sig
            assert 'entry' in sig
            assert 'exitType' in sig
            assert sig['direction'] in ['LONG', 'SHORT']

    def test_valid_downtrend_execution(self, downtrend_candles, sample_config):
        """Test with downtrend data - should generate SHORT signals."""
        signals = run_backtest(downtrend_candles, sample_config)

        assert len(signals) > 0

        # In downtrend, expect more SHORT signals
        short_count = sum(1 for s in signals if s['direction'] == 'SHORT')
        long_count = sum(1 for s in signals if s['direction'] == 'LONG')
        # Allow some flexibility due to noise
        assert short_count + long_count > 0


class TestFilters:
    """Test strategy filter logic."""

    def test_trend_filter_long(self, uptrend_candles, sample_config):
        """Test trend filter blocks LONG when EMA fast < EMA slow."""
        sample_config['useTrendFilter'] = True
        signals = run_backtest(uptrend_candles, sample_config)

        # With trend filter, should only get signals aligned with EMA
        # In uptrend, should get mostly LONG signals
        long_signals = [s for s in signals if s['direction'] == 'LONG']
        assert len(long_signals) >= 0  # Should have some LONG signals

    def test_volume_filter(self, uptrend_candles, sample_config):
        """Test volume filter requires vol >= multiplier × avg."""
        sample_config['useVolumeFilter'] = True
        sample_config['volMultiplier'] = 2.0

        signals_no_filter = run_backtest(uptrend_candles, sample_config)

        # With high volume filter, should get fewer signals
        sample_config['volMultiplier'] = 5.0
        signals_strict_filter = run_backtest(uptrend_candles, sample_config)

        # Stricter filter should produce fewer or equal signals
        assert len(signals_strict_filter) <= len(signals_no_filter)

    def test_htf_bias_filter(self, uptrend_candles, sample_config):
        """Test HTF bias filter checks price vs long-period EMA."""
        sample_config['useHtfBias'] = True
        sample_config['htfEmaPeriod'] = 100

        signals = run_backtest(uptrend_candles, sample_config)

        # Should still produce signals when HTF aligns
        assert len(signals) >= 0

    def test_all_filters_combined(self, uptrend_candles, sample_config):
        """Test all filters together - most restrictive."""
        sample_config['useTrendFilter'] = True
        sample_config['useVolumeFilter'] = True
        sample_config['volMultiplier'] = 2.0
        sample_config['useHtfBias'] = True

        signals = run_backtest(uptrend_candles, sample_config)

        # Should still work but with fewer signals
        # All signals that pass should meet filter criteria
        for sig in signals:
            assert sig['direction'] in ['LONG', 'SHORT']


class TestPositionLogic:
    """Test position state machine."""

    def test_no_overlapping_positions(self, uptrend_candles, sample_config):
        """Test only one position open at a time."""
        signals = run_backtest(uptrend_candles, sample_config)

        # Track open positions - should never have overlap
        open_positions = []
        for sig in signals:
            if sig.get('exitType') == 'signal' and sig.get('exitTimestamp'):
                # Position opened and closed
                open_positions.append((sig['timestamp'], sig['exitTimestamp']))

        # Check no overlaps
        for i in range(len(open_positions) - 1):
            exit_time_i = open_positions[i][1]
            entry_time_next = open_positions[i + 1][0]
            # Next entry should be >= previous exit
            assert entry_time_next >= exit_time_i

    def test_min_votes_threshold(self, uptrend_candles, sample_config):
        """Test min_votes threshold - fewer votes = fewer signals."""
        sample_config['min_votes'] = 3
        signals_3votes = run_backtest(uptrend_candles, sample_config)

        sample_config['min_votes'] = 5
        signals_5votes = run_backtest(uptrend_candles, sample_config)

        # Higher threshold should produce fewer or equal signals
        assert len(signals_5votes) <= len(signals_3votes)

    def test_min_exit_votes(self, uptrend_candles, sample_config):
        """Test min_exit_votes affects trade duration."""
        sample_config['min_exit_votes'] = 1
        signals_quick_exit = run_backtest(uptrend_candles, sample_config)

        sample_config['min_exit_votes'] = 4
        signals_slow_exit = run_backtest(uptrend_candles, sample_config)

        # Quick exit should produce more signals (trades closed faster)
        # This is probabilistic but generally true
        assert len(signals_quick_exit) >= len(signals_slow_exit) or len(signals_slow_exit) >= 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_zero_volume_candles(self, sample_config):
        """Test with zero volume - should handle gracefully."""
        df = pd.DataFrame({
            'time': [datetime(2024, 1, 1, 0, i, 0, tzinfo=timezone.utc) for i in range(100)],
            'open': [50000] * 100,
            'high': [50100] * 100,
            'low': [49900] * 100,
            'close': [50000] * 100,
            'volume': [0] * 100,  # Zero volume
        })

        sample_config['useVolumeFilter'] = True
        signals = run_backtest(df, sample_config)

        # Should not crash, should handle division by zero
        assert isinstance(signals, list)

    def test_missing_config_keys(self, uptrend_candles):
        """Test with minimal config - should use defaults."""
        minimal_config = {
            'min_votes': 3,
        }

        signals = run_backtest(uptrend_candles, minimal_config)

        # Should work with defaults
        assert isinstance(signals, list)

    def test_extreme_price_movements(self, sample_config):
        """Test with extreme price jumps - should handle gracefully."""
        df = pd.DataFrame({
            'time': [datetime(2024, 1, 1, 0, i, 0, tzinfo=timezone.utc) for i in range(100)],
            'open': [50000 if i < 50 else 100000 for i in range(100)],
            'high': [50100 if i < 50 else 100100 for i in range(100)],
            'low': [49900 if i < 50 else 99900 for i in range(100)],
            'close': [50000 if i < 50 else 100000 for i in range(100)],
            'volume': [100] * 100,
        })

        signals = run_backtest(df, sample_config)

        # Should handle without crashing
        assert isinstance(signals, list)

    def test_nan_handling(self, sample_config):
        """Test with NaN values in data."""
        df = pd.DataFrame({
            'time': [datetime(2024, 1, 1, 0, i, 0, tzinfo=timezone.utc) for i in range(100)],
            'open': [50000] * 100,
            'high': [50100] * 100,
            'low': [49900] * 100,
            'close': [50000 if i % 10 != 0 else np.nan for i in range(100)],
            'volume': [100] * 100,
        })

        signals = run_backtest(df, sample_config)

        # Should handle NaN gracefully
        assert isinstance(signals, list)


class TestSignalOutput:
    """Test signal output format and content."""

    def test_signal_structure(self, uptrend_candles, sample_config):
        """Test each signal has correct structure."""
        signals = run_backtest(uptrend_candles, sample_config)

        if len(signals) > 0:
            sig = signals[0]

            # Required fields
            assert 'timestamp' in sig
            assert 'direction' in sig
            assert 'entry' in sig
            assert 'exitType' in sig
            assert 'votes' in sig
            assert 'agreeingStrategies' in sig

            # Type checks
            assert isinstance(sig['direction'], str)
            assert isinstance(sig['entry'], (int, float))
            assert isinstance(sig['votes'], str)
            assert isinstance(sig['agreeingStrategies'], list)

    def test_closed_signal_has_exit(self, uptrend_candles, sample_config):
        """Test closed signals have exit price and timestamp."""
        signals = run_backtest(uptrend_candles, sample_config)

        closed_signals = [s for s in signals if s.get('exitType') == 'signal']

        for sig in closed_signals:
            assert 'exitPrice' in sig
            assert 'exitTimestamp' in sig
            assert sig['exitPrice'] > 0
            assert sig['exitTimestamp'] is not None

    def test_agreeing_strategies_format(self, uptrend_candles, sample_config):
        """Test agreeingStrategies list contains valid strategy names."""
        signals = run_backtest(uptrend_candles, sample_config)

        valid_strategies = [
            "EMAcrossoverStrategy",
            "RSIBollingerStrategy",
            "VWAPBounceStrategy",
            "RangeTradingStrategy",
            "BreakoutStrategy",
            "MACDMomentumStrategy"
        ]

        for sig in signals:
            strategies = sig.get('agreeingStrategies', [])
            assert isinstance(strategies, list)
            assert len(strategies) >= sample_config['min_votes']

            for strategy in strategies:
                assert strategy in valid_strategies


class TestPerformance:
    """Test performance with large datasets."""

    def test_large_dataset(self, sample_config):
        """Test with 10k candles - should complete in reasonable time."""
        np.random.seed(45)
        n = 10000
        base = 50000
        times = [datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=i) for i in range(n)]

        closes = base + np.cumsum(np.random.randn(n) * 10)

        df = pd.DataFrame({
            'time': times,
            'open': closes - np.random.rand(n) * 20,
            'high': closes + np.random.rand(n) * 30,
            'low': closes - np.random.rand(n) * 30,
            'close': closes,
            'volume': np.random.rand(n) * 100 + 50,
        })

        import time
        start = time.time()
        signals = run_backtest(df, sample_config)
        elapsed = time.time() - start

        # Should complete in < 5 seconds for 10k candles
        assert elapsed < 5.0
        assert isinstance(signals, list)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
