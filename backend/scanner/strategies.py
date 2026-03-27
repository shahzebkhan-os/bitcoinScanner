"""
Trading Strategies Module - scanner/strategies.py

Responsibilities:
- Implement 6 scalping strategy evaluators
- Each strategy votes LONG / SHORT / NEUTRAL
- Return SignalResult with direction, strength, and reason
"""

import logging
from dataclasses import dataclass
from typing import Optional
import pandas as pd

from scanner.indicators import IndicatorSnapshot

logger = logging.getLogger(__name__)


@dataclass
class SignalResult:
    """Result from a single strategy evaluation."""
    strategy_name: str
    direction: str  # "LONG", "SHORT", "NEUTRAL"
    strength: float  # 0.0 to 1.0
    reason: str


class EMAcrossoverStrategy:
    """Strategy 1: EMA Crossover"""

    def evaluate(self, snapshot: IndicatorSnapshot, config: dict) -> SignalResult:
        """
        LONG when ema_fast just crossed ABOVE ema_slow (within last 2 candles)
        SHORT when ema_fast just crossed BELOW ema_slow
        NEUTRAL otherwise
        """
        if snapshot.ema_crossover == "bullish":
            return SignalResult(
                strategy_name="EMAcrossoverStrategy",
                direction="LONG",
                strength=0.75,
                reason="EMA fast crossed above EMA slow (bullish crossover)"
            )
        elif snapshot.ema_crossover == "bearish":
            return SignalResult(
                strategy_name="EMAcrossoverStrategy",
                direction="SHORT",
                strength=0.75,
                reason="EMA fast crossed below EMA slow (bearish crossover)"
            )
        else:
            return SignalResult(
                strategy_name="EMAcrossoverStrategy",
                direction="NEUTRAL",
                strength=0.0,
                reason="No EMA crossover detected"
            )


class RSIBollingerStrategy:
    """Strategy 2: RSI + Bollinger Bands"""

    def evaluate(self, snapshot: IndicatorSnapshot, config: dict) -> SignalResult:
        """
        LONG when rsi < rsi_oversold AND close_vs_bb == "below_lower"
        SHORT when rsi > rsi_overbought AND close_vs_bb == "above_upper"
        NEUTRAL otherwise
        """
        ind_config = config.get('indicators', {})
        rsi_oversold = ind_config.get('rsi_oversold', 30)
        rsi_overbought = ind_config.get('rsi_overbought', 70)

        if snapshot.rsi < rsi_oversold and snapshot.close_vs_bb == "below_lower":
            return SignalResult(
                strategy_name="RSIBollingerStrategy",
                direction="LONG",
                strength=0.80,
                reason=f"RSI oversold ({snapshot.rsi:.1f}) and price below lower BB"
            )
        elif snapshot.rsi > rsi_overbought and snapshot.close_vs_bb == "above_upper":
            return SignalResult(
                strategy_name="RSIBollingerStrategy",
                direction="SHORT",
                strength=0.80,
                reason=f"RSI overbought ({snapshot.rsi:.1f}) and price above upper BB"
            )
        else:
            return SignalResult(
                strategy_name="RSIBollingerStrategy",
                direction="NEUTRAL",
                strength=0.0,
                reason=f"RSI at {snapshot.rsi:.1f}, no extreme condition"
            )


class VWAPBounceStrategy:
    """Strategy 3: VWAP Bounce"""

    def evaluate(self, snapshot: IndicatorSnapshot, config: dict, prev_snapshot: Optional[IndicatorSnapshot] = None) -> SignalResult:
        """
        LONG when price crossed from below VWAP to above VWAP AND volume_ratio > 1.2
        SHORT when price crossed from above VWAP to below VWAP AND volume_ratio > 1.2
        NEUTRAL otherwise
        """
        # Check volume condition
        if snapshot.volume_ratio <= 1.2:
            return SignalResult(
                strategy_name="VWAPBounceStrategy",
                direction="NEUTRAL",
                strength=0.0,
                reason="Volume too low for VWAP signal"
            )

        # For simplicity, use close_vs_vwap (in production, track previous state)
        if snapshot.close_vs_vwap == "above" and snapshot.volume_ratio > 1.2:
            return SignalResult(
                strategy_name="VWAPBounceStrategy",
                direction="LONG",
                strength=0.70,
                reason=f"Price above VWAP with high volume ({snapshot.volume_ratio:.2f}x)"
            )
        elif snapshot.close_vs_vwap == "below" and snapshot.volume_ratio > 1.2:
            return SignalResult(
                strategy_name="VWAPBounceStrategy",
                direction="SHORT",
                strength=0.70,
                reason=f"Price below VWAP with high volume ({snapshot.volume_ratio:.2f}x)"
            )
        else:
            return SignalResult(
                strategy_name="VWAPBounceStrategy",
                direction="NEUTRAL",
                strength=0.0,
                reason="No VWAP cross detected"
            )


class RangeTradingStrategy:
    """Strategy 4: Range Trading"""

    def evaluate(self, snapshot: IndicatorSnapshot, config: dict, df: Optional[pd.DataFrame] = None) -> SignalResult:
        """
        Detect range over last 20 candles (range_size < 1.5% = sideways)
        LONG when price within 0.1% of range_low AND rsi < 45
        SHORT when price within 0.1% of range_high AND rsi > 55
        NEUTRAL when trending (range_size > 1.5%)
        """
        if df is None or len(df) < 20:
            return SignalResult(
                strategy_name="RangeTradingStrategy",
                direction="NEUTRAL",
                strength=0.0,
                reason="Insufficient data for range detection"
            )

        # Calculate range over last 20 candles
        recent = df.tail(20)
        range_high = recent['high'].max()
        range_low = recent['low'].min()
        range_size_pct = ((range_high - range_low) / range_low) * 100

        # Check if ranging
        if range_size_pct > 1.5:
            return SignalResult(
                strategy_name="RangeTradingStrategy",
                direction="NEUTRAL",
                strength=0.0,
                reason=f"Market trending (range: {range_size_pct:.2f}%)"
            )

        # Check if near range boundaries
        price = snapshot.current_price
        near_low = abs(price - range_low) / range_low < 0.001  # 0.1%
        near_high = abs(price - range_high) / range_high < 0.001  # 0.1%

        if near_low and snapshot.rsi < 45:
            return SignalResult(
                strategy_name="RangeTradingStrategy",
                direction="LONG",
                strength=0.65,
                reason=f"Price near range low with RSI {snapshot.rsi:.1f}"
            )
        elif near_high and snapshot.rsi > 55:
            return SignalResult(
                strategy_name="RangeTradingStrategy",
                direction="SHORT",
                strength=0.65,
                reason=f"Price near range high with RSI {snapshot.rsi:.1f}"
            )
        else:
            return SignalResult(
                strategy_name="RangeTradingStrategy",
                direction="NEUTRAL",
                strength=0.0,
                reason="Price not at range boundaries"
            )


class BreakoutStrategy:
    """Strategy 5: Breakout"""

    def evaluate(self, snapshot: IndicatorSnapshot, config: dict, df: Optional[pd.DataFrame] = None) -> SignalResult:
        """
        LONG when close > range_high * 1.002 AND volume_ratio > 1.5
        SHORT when close < range_low * 0.998 AND volume_ratio > 1.5
        NEUTRAL otherwise (complements Strategy 4)
        """
        if df is None or len(df) < 20:
            return SignalResult(
                strategy_name="BreakoutStrategy",
                direction="NEUTRAL",
                strength=0.0,
                reason="Insufficient data for breakout detection"
            )

        # Calculate range over last 20 candles
        recent = df.tail(20)
        range_high = recent['high'].max()
        range_low = recent['low'].min()

        price = snapshot.current_price

        # Check for breakout with volume
        if price > range_high * 1.002 and snapshot.volume_ratio > 1.5:
            return SignalResult(
                strategy_name="BreakoutStrategy",
                direction="LONG",
                strength=0.85,
                reason=f"Bullish breakout with high volume ({snapshot.volume_ratio:.2f}x)"
            )
        elif price < range_low * 0.998 and snapshot.volume_ratio > 1.5:
            return SignalResult(
                strategy_name="BreakoutStrategy",
                direction="SHORT",
                strength=0.85,
                reason=f"Bearish breakdown with high volume ({snapshot.volume_ratio:.2f}x)"
            )
        else:
            return SignalResult(
                strategy_name="BreakoutStrategy",
                direction="NEUTRAL",
                strength=0.0,
                reason="No breakout detected"
            )


class MACDMomentumStrategy:
    """Strategy 6: MACD Momentum"""

    def evaluate(self, snapshot: IndicatorSnapshot, config: dict) -> SignalResult:
        """
        LONG when macd_cross == "bullish" AND macd_histogram > 0 AND close_vs_vwap == "above"
        SHORT when macd_cross == "bearish" AND macd_histogram < 0 AND close_vs_vwap == "below"
        NEUTRAL otherwise
        """
        if (snapshot.macd_cross == "bullish" and
            snapshot.macd_histogram > 0 and
            snapshot.close_vs_vwap == "above"):
            return SignalResult(
                strategy_name="MACDMomentumStrategy",
                direction="LONG",
                strength=0.78,
                reason="Bullish MACD cross with positive histogram and price above VWAP"
            )
        elif (snapshot.macd_cross == "bearish" and
              snapshot.macd_histogram < 0 and
              snapshot.close_vs_vwap == "below"):
            return SignalResult(
                strategy_name="MACDMomentumStrategy",
                direction="SHORT",
                strength=0.78,
                reason="Bearish MACD cross with negative histogram and price below VWAP"
            )
        else:
            return SignalResult(
                strategy_name="MACDMomentumStrategy",
                direction="NEUTRAL",
                strength=0.0,
                reason="MACD conditions not met for signal"
            )


def run_all_strategies(snapshot: IndicatorSnapshot, config: dict, df: Optional[pd.DataFrame] = None) -> list[SignalResult]:
    """
    Run all 6 strategies and return list of results.

    Args:
        snapshot: Current indicator snapshot
        config: Configuration dict
        df: Optional DataFrame for range/breakout strategies

    Returns:
        List of SignalResult from all strategies
    """
    results = []

    try:
        # Strategy 1: EMA Crossover
        strategy1 = EMAcrossoverStrategy()
        results.append(strategy1.evaluate(snapshot, config))

        # Strategy 2: RSI + Bollinger
        strategy2 = RSIBollingerStrategy()
        results.append(strategy2.evaluate(snapshot, config))

        # Strategy 3: VWAP Bounce
        strategy3 = VWAPBounceStrategy()
        results.append(strategy3.evaluate(snapshot, config))

        # Strategy 4: Range Trading
        strategy4 = RangeTradingStrategy()
        results.append(strategy4.evaluate(snapshot, config, df))

        # Strategy 5: Breakout
        strategy5 = BreakoutStrategy()
        results.append(strategy5.evaluate(snapshot, config, df))

        # Strategy 6: MACD Momentum
        strategy6 = MACDMomentumStrategy()
        results.append(strategy6.evaluate(snapshot, config))

    except Exception as e:
        logger.error(f"Error running strategies: {e}", exc_info=True)

    return results
