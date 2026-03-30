"""
Indicator Calculations Module - scanner/indicators.py

Responsibilities:
- Calculate 6 technical indicators on candle data
- Return IndicatorSnapshot dataclass with all values
- Handle NaN values gracefully
"""

import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class IndicatorSnapshot:
    """Snapshot of all indicator values at a specific time."""
    ema_fast: float
    ema_slow: float
    ema_crossover: str  # "bullish", "bearish", "none"
    rsi: float
    macd_line: float
    macd_signal: float
    macd_histogram: float
    macd_cross: str  # "bullish", "bearish", "none"
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_bandwidth: float
    close_vs_bb: str  # "above_upper", "below_lower", "inside"
    vwap: float
    close_vs_vwap: str  # "above", "below"
    current_volume: float
    avg_volume: float
    volume_ratio: float
    current_price: float
    timestamp: datetime
    # Signal accuracy enhancement fields (optional, default-safe for backward compat)
    atr: float = 0.0                     # Average True Range (14-period)
    ema_spread_pct: float = 0.0          # EMA fast-slow spread as % of price
    prev_close_vs_vwap: str = "above"    # Previous candle's close vs VWAP

    def to_dict(self) -> dict:
        """Serialize to JSON-safe camelCase dict for WebSocket broadcast."""
        return {
            "emaFast": round(self.ema_fast, 4),
            "emaSlow": round(self.ema_slow, 4),
            "emaCrossover": self.ema_crossover,
            "rsi": round(self.rsi, 4),
            "macdLine": round(self.macd_line, 4),
            "macdSignal": round(self.macd_signal, 4),
            "macdHistogram": round(self.macd_histogram, 4),
            "macdCross": self.macd_cross,
            "bbUpper": round(self.bb_upper, 4),
            "bbMiddle": round(self.bb_middle, 4),
            "bbLower": round(self.bb_lower, 4),
            "bbBandwidth": round(self.bb_bandwidth, 4),
            "closeVsBb": self.close_vs_bb,
            "vwap": round(self.vwap, 4),
            "closeVsVwap": self.close_vs_vwap,
            "currentVolume": round(self.current_volume, 4),
            "avgVolume": round(self.avg_volume, 4),
            "volumeRatio": round(self.volume_ratio, 4),
            "currentPrice": round(self.current_price, 4),
            "timestamp": self.timestamp.isoformat(),
            "atr": round(self.atr, 4),
            "emaSpreadPct": round(self.ema_spread_pct, 6),
            "prevCloseVsVwap": self.prev_close_vs_vwap,
        }


def calculate_indicators(df: pd.DataFrame, config: dict) -> Optional[IndicatorSnapshot]:
    """
    Calculate all technical indicators on the provided DataFrame.

    Args:
        df: DataFrame with columns [time, open, high, low, close, volume]
        config: Configuration dict with indicator parameters

    Returns:
        IndicatorSnapshot with all indicator values, or None if calculation fails
    """
    try:
        if df.empty or len(df) < 50:
            logger.warning("Insufficient data for indicator calculation")
            return None

        # Make a copy to avoid modifying original
        data = df.copy()

        # Extract config parameters
        ind_config = config.get('indicators', {})
        ema_fast_period = ind_config.get('ema_fast', 9)
        ema_slow_period = ind_config.get('ema_slow', 21)
        rsi_period = ind_config.get('rsi_period', 14)
        macd_fast = ind_config.get('macd_fast', 12)
        macd_slow = ind_config.get('macd_slow', 26)
        macd_signal_period = ind_config.get('macd_signal', 9)
        bb_period = ind_config.get('bb_period', 20)
        bb_std = ind_config.get('bb_std', 2)

        # 1. EMA Calculations
        data['ema_fast'] = data['close'].ewm(span=ema_fast_period, adjust=False).mean()
        data['ema_slow'] = data['close'].ewm(span=ema_slow_period, adjust=False).mean()

        # Detect EMA crossover
        data['ema_fast_prev'] = data['ema_fast'].shift(1)
        data['ema_slow_prev'] = data['ema_slow'].shift(1)

        # 2. RSI Calculation — Wilder's smoothing via EWM (matches TradingView)
        delta = data['close'].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta.where(delta < 0, 0.0))
        # EWM with alpha=1/period replicates Wilder's method
        alpha = 1.0 / rsi_period
        avg_gain = gain.ewm(alpha=alpha, adjust=False).mean()
        avg_loss = loss.ewm(alpha=alpha, adjust=False).mean()
        # Edge cases: avg_loss == 0 → RSI 100 (pure uptrend) or 50 (no movement)
        rsi_series = pd.Series(50.0, index=data.index)
        normal = avg_loss > 0
        rs = avg_gain[normal] / avg_loss[normal]
        rsi_series[normal] = 100.0 - (100.0 / (1.0 + rs))
        rsi_series[(avg_loss == 0) & (avg_gain > 0)] = 100.0
        data['rsi'] = rsi_series.fillna(50.0)

        # 3. MACD Calculation
        ema_fast_macd = data['close'].ewm(span=macd_fast, adjust=False).mean()
        ema_slow_macd = data['close'].ewm(span=macd_slow, adjust=False).mean()
        data['macd_line'] = ema_fast_macd - ema_slow_macd
        data['macd_signal'] = data['macd_line'].ewm(span=macd_signal_period, adjust=False).mean()
        data['macd_histogram'] = data['macd_line'] - data['macd_signal']

        # Detect MACD crossover (histogram sign flip)
        data['macd_hist_prev'] = data['macd_histogram'].shift(1)

        # 4. Bollinger Bands
        data['bb_middle'] = data['close'].rolling(window=bb_period).mean()
        bb_std_dev = data['close'].rolling(window=bb_period).std()
        data['bb_upper'] = data['bb_middle'] + (bb_std_dev * bb_std)
        data['bb_lower'] = data['bb_middle'] - (bb_std_dev * bb_std)
        data['bb_bandwidth'] = (data['bb_upper'] - data['bb_lower']) / data['bb_middle']

        # 5. VWAP Calculation (simplified - resets at start of data)
        typical_price = (data['high'] + data['low'] + data['close']) / 3
        data['vwap'] = (typical_price * data['volume']).cumsum() / data['volume'].cumsum()

        # 6. Volume Analysis
        data['avg_volume'] = data['volume'].rolling(window=20).mean()
        data['volume_ratio'] = data['volume'] / data['avg_volume']

        # 7. ATR (Average True Range, 14-period) for volatility-aware filtering
        data['tr0'] = abs(data['high'] - data['low'])
        data['tr1'] = abs(data['high'] - data['close'].shift(1))
        data['tr2'] = abs(data['low'] - data['close'].shift(1))
        data['tr'] = data[['tr0', 'tr1', 'tr2']].max(axis=1)
        data['atr'] = data['tr'].ewm(span=14, adjust=False).mean()

        # Get latest values
        latest = data.iloc[-1]
        prev = data.iloc[-2] if len(data) > 1 else latest

        # Determine EMA crossover
        ema_crossover = "none"
        if pd.notna(latest['ema_fast']) and pd.notna(latest['ema_slow']):
            if pd.notna(prev['ema_fast']) and pd.notna(prev['ema_slow']):
                if prev['ema_fast'] <= prev['ema_slow'] and latest['ema_fast'] > latest['ema_slow']:
                    ema_crossover = "bullish"
                elif prev['ema_fast'] >= prev['ema_slow'] and latest['ema_fast'] < latest['ema_slow']:
                    ema_crossover = "bearish"

        # Determine MACD crossover
        macd_cross = "none"
        if pd.notna(latest['macd_histogram']) and pd.notna(prev.get('macd_histogram')):
            if prev['macd_histogram'] <= 0 and latest['macd_histogram'] > 0:
                macd_cross = "bullish"
            elif prev['macd_histogram'] >= 0 and latest['macd_histogram'] < 0:
                macd_cross = "bearish"

        # Determine close vs Bollinger Bands
        close_vs_bb = "inside"
        if pd.notna(latest['close']) and pd.notna(latest['bb_upper']) and pd.notna(latest['bb_lower']):
            if latest['close'] > latest['bb_upper']:
                close_vs_bb = "above_upper"
            elif latest['close'] < latest['bb_lower']:
                close_vs_bb = "below_lower"

        # Determine close vs VWAP
        close_vs_vwap = "above" if latest['close'] > latest['vwap'] else "below"

        # Determine previous close vs VWAP (for crossover detection)
        prev_close_vs_vwap = "above" if prev['close'] > prev['vwap'] else "below"

        # EMA spread as % of price (guards against whipsaw signals when EMAs are too close)
        ema_spread_pct = 0.0
        if pd.notna(latest['ema_fast']) and pd.notna(latest['ema_slow']) and latest['ema_slow'] > 0:
            ema_spread_pct = abs(latest['ema_fast'] - latest['ema_slow']) / latest['ema_slow']

        # Create snapshot
        snapshot = IndicatorSnapshot(
            ema_fast=float(latest['ema_fast']) if pd.notna(latest['ema_fast']) else 0.0,
            ema_slow=float(latest['ema_slow']) if pd.notna(latest['ema_slow']) else 0.0,
            ema_crossover=ema_crossover,
            rsi=float(latest['rsi']) if pd.notna(latest['rsi']) else 50.0,
            macd_line=float(latest['macd_line']) if pd.notna(latest['macd_line']) else 0.0,
            macd_signal=float(latest['macd_signal']) if pd.notna(latest['macd_signal']) else 0.0,
            macd_histogram=float(latest['macd_histogram']) if pd.notna(latest['macd_histogram']) else 0.0,
            macd_cross=macd_cross,
            bb_upper=float(latest['bb_upper']) if pd.notna(latest['bb_upper']) else 0.0,
            bb_middle=float(latest['bb_middle']) if pd.notna(latest['bb_middle']) else 0.0,
            bb_lower=float(latest['bb_lower']) if pd.notna(latest['bb_lower']) else 0.0,
            bb_bandwidth=float(latest['bb_bandwidth']) if pd.notna(latest['bb_bandwidth']) else 0.0,
            close_vs_bb=close_vs_bb,
            vwap=float(latest['vwap']) if pd.notna(latest['vwap']) else 0.0,
            close_vs_vwap=close_vs_vwap,
            current_volume=float(latest['volume']) if pd.notna(latest['volume']) else 0.0,
            avg_volume=float(latest['avg_volume']) if pd.notna(latest['avg_volume']) else 0.0,
            volume_ratio=float(latest['volume_ratio']) if pd.notna(latest['volume_ratio']) else 1.0,
            current_price=float(latest['close']) if pd.notna(latest['close']) else 0.0,
            timestamp=latest['time'] if 'time' in latest.index else datetime.utcnow(),
            atr=float(latest['atr']) if pd.notna(latest['atr']) else 0.0,
            ema_spread_pct=ema_spread_pct,
            prev_close_vs_vwap=prev_close_vs_vwap,
        )

        return snapshot

    except Exception as e:
        logger.error(f"Error calculating indicators: {e}", exc_info=True)
        return None
