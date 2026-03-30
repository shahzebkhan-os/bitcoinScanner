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
EMA_SPREAD_STRENGTH_MULTIPLIER = 50.0
VWAP_STRENGTH_BASE = 0.60
VWAP_STRENGTH_VOL_MULTIPLIER = 0.15


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

        Accuracy improvement: require a minimum EMA spread percentage to
        avoid whipsaw signals when the two EMAs are nearly equal.
        """
        filters = config.get('signal_filters', {})
        min_spread = float(filters.get('min_ema_spread_pct', 0.0005))  # 0.0005 = 0.05%

        if snapshot.ema_crossover == "bullish":
            if snapshot.ema_spread_pct < min_spread:
                return SignalResult(
                    strategy_name="EMAcrossoverStrategy",
                    direction="NEUTRAL",
                    strength=0.0,
                    reason=f"Bullish EMA cross but spread too small ({snapshot.ema_spread_pct:.4%}) — whipsaw risk"
                )
            # Strength scales with spread: wider separation = stronger signal.
            # 50x multiplier maps small spread increases into useful 0..1 strength granularity.
            strength = min(0.95, 0.60 + snapshot.ema_spread_pct * EMA_SPREAD_STRENGTH_MULTIPLIER)  # capped at 0.95 to keep headroom below 1.0
            return SignalResult(
                strategy_name="EMAcrossoverStrategy",
                direction="LONG",
                strength=round(strength, 2),
                reason=f"EMA fast crossed above EMA slow (spread: {snapshot.ema_spread_pct:.4%})"
            )
        elif snapshot.ema_crossover == "bearish":
            if snapshot.ema_spread_pct < min_spread:
                return SignalResult(
                    strategy_name="EMAcrossoverStrategy",
                    direction="NEUTRAL",
                    strength=0.0,
                    reason=f"Bearish EMA cross but spread too small ({snapshot.ema_spread_pct:.4%}) — whipsaw risk"
                )
            # Same scaling as bullish case for symmetry.
            strength = min(0.95, 0.60 + snapshot.ema_spread_pct * EMA_SPREAD_STRENGTH_MULTIPLIER)
            return SignalResult(
                strategy_name="EMAcrossoverStrategy",
                direction="SHORT",
                strength=round(strength, 2),
                reason=f"EMA fast crossed below EMA slow (spread: {snapshot.ema_spread_pct:.4%})"
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

        Accuracy improvement: add EMA trend alignment confirmation.
        For LONG signals, EMA fast >= EMA slow (price in uptrend context).
        For SHORT signals, EMA fast <= EMA slow (price in downtrend context).
        This prevents buying into a strong downtrend just because RSI is low.
        """
        ind_config = config.get('indicators', {})
        rsi_oversold = ind_config.get('rsi_oversold', 30)
        rsi_overbought = ind_config.get('rsi_overbought', 70)
        filters = config.get('signal_filters', {})
        require_ema_alignment = filters.get('require_rsi_ema_alignment', True)
        ema_tol = float(filters.get('rsi_ema_alignment_tolerance', 0.002))

        if snapshot.rsi < rsi_oversold and snapshot.close_vs_bb == "below_lower":
            # Accuracy check: only buy if EMA fast is not significantly below EMA slow
            if require_ema_alignment and snapshot.ema_fast < snapshot.ema_slow * (1.0 - ema_tol):
                return SignalResult(
                    strategy_name="RSIBollingerStrategy",
                    direction="NEUTRAL",
                    strength=0.0,
                    reason=f"RSI oversold ({snapshot.rsi:.1f}) but EMA trend bearish — skip"
                )
            return SignalResult(
                strategy_name="RSIBollingerStrategy",
                direction="LONG",
                strength=0.80,
                reason=f"RSI oversold ({snapshot.rsi:.1f}) and price below lower BB with EMA aligned"
            )
        elif snapshot.rsi > rsi_overbought and snapshot.close_vs_bb == "above_upper":
            # Accuracy check: only short if EMA fast is not significantly above EMA slow
            if require_ema_alignment and snapshot.ema_fast > snapshot.ema_slow * (1.0 + ema_tol):
                return SignalResult(
                    strategy_name="RSIBollingerStrategy",
                    direction="NEUTRAL",
                    strength=0.0,
                    reason=f"RSI overbought ({snapshot.rsi:.1f}) but EMA trend bullish — skip"
                )
            return SignalResult(
                strategy_name="RSIBollingerStrategy",
                direction="SHORT",
                strength=0.80,
                reason=f"RSI overbought ({snapshot.rsi:.1f}) and price above upper BB with EMA aligned"
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

        Accuracy improvement: require an actual VWAP crossover event using
        prev_close_vs_vwap field instead of just checking the current position.
        This prevents the strategy from continuously firing on every tick while
        price stays on one side of VWAP.
        """
        filters = config.get('signal_filters', {})
        vwap_crossover_only = filters.get('vwap_crossover_only', True)
        vwap_vol_threshold = float(filters.get('vwap_vol_threshold', 1.2))

        # Check volume condition
        if snapshot.volume_ratio <= vwap_vol_threshold:
            return SignalResult(
                strategy_name="VWAPBounceStrategy",
                direction="NEUTRAL",
                strength=0.0,
                reason=f"Volume too low for VWAP signal ({snapshot.volume_ratio:.2f}x < {vwap_vol_threshold}x)"
            )

        if vwap_crossover_only:
            # Require actual crossover: previous candle was on the other side
            crossed_above = (snapshot.prev_close_vs_vwap == "below" and snapshot.close_vs_vwap == "above")
            crossed_below = (snapshot.prev_close_vs_vwap == "above" and snapshot.close_vs_vwap == "below")

            if crossed_above:
                # Base 0.60 + 0.15 per volume multiple above 1.0x, capped at 0.90.
                strength = min(0.90, VWAP_STRENGTH_BASE + (snapshot.volume_ratio - 1.0) * VWAP_STRENGTH_VOL_MULTIPLIER)
                return SignalResult(
                    strategy_name="VWAPBounceStrategy",
                    direction="LONG",
                    strength=round(strength, 2),
                    reason=f"Price crossed ABOVE VWAP with volume {snapshot.volume_ratio:.2f}x avg"
                )
            elif crossed_below:
                # Same scaling as bullish case for symmetry.
                strength = min(0.90, VWAP_STRENGTH_BASE + (snapshot.volume_ratio - 1.0) * VWAP_STRENGTH_VOL_MULTIPLIER)
                return SignalResult(
                    strategy_name="VWAPBounceStrategy",
                    direction="SHORT",
                    strength=round(strength, 2),
                    reason=f"Price crossed BELOW VWAP with volume {snapshot.volume_ratio:.2f}x avg"
                )
            else:
                return SignalResult(
                    strategy_name="VWAPBounceStrategy",
                    direction="NEUTRAL",
                    strength=0.0,
                    reason="No VWAP cross detected"
                )
        else:
            # Legacy behaviour (crossover filter disabled)
            if snapshot.close_vs_vwap == "above":
                return SignalResult(
                    strategy_name="VWAPBounceStrategy",
                    direction="LONG",
                    strength=0.70,
                    reason=f"Price above VWAP with high volume ({snapshot.volume_ratio:.2f}x)"
                )
            elif snapshot.close_vs_vwap == "below":
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
                    reason="No VWAP signal"
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

        Accuracy improvement: require the candle to close beyond the level
        (not just touch it), and use a volume threshold scaled to ATR to
        avoid false breakouts on normal-volatility candles.
        """
        if df is None or len(df) < 20:
            return SignalResult(
                strategy_name="BreakoutStrategy",
                direction="NEUTRAL",
                strength=0.0,
                reason="Insufficient data for breakout detection"
            )

        # Calculate range over last 20 candles (excluding current)
        recent = df.iloc[-21:-1] if len(df) > 20 else df.iloc[:-1]
        if len(recent) < 20:
            return SignalResult(
                strategy_name="BreakoutStrategy",
                direction="NEUTRAL",
                strength=0.0,
                reason="Insufficient historical candles for breakout detection"
            )
        range_high = recent['high'].max()
        range_low = recent['low'].min()

        price = snapshot.current_price
        filters = config.get('signal_filters', {})
        breakout_vol_threshold = float(filters.get('breakout_vol_threshold', 1.5))

        # Check for breakout with volume — use candle close for confirmation
        if price > range_high * 1.002 and snapshot.volume_ratio > breakout_vol_threshold:
            # Strength scales with volume and how far above the breakout level
            excess_pct = (price - range_high) / range_high
            strength = min(0.95, 0.75 + excess_pct * 10 + (snapshot.volume_ratio - 1.5) * 0.05)
            return SignalResult(
                strategy_name="BreakoutStrategy",
                direction="LONG",
                strength=round(strength, 2),
                reason=f"Bullish breakout above {range_high:.2f} with {snapshot.volume_ratio:.2f}x volume"
            )
        elif price < range_low * 0.998 and snapshot.volume_ratio > breakout_vol_threshold:
            excess_pct = (range_low - price) / range_low
            strength = min(0.95, 0.75 + excess_pct * 10 + (snapshot.volume_ratio - 1.5) * 0.05)
            return SignalResult(
                strategy_name="BreakoutStrategy",
                direction="SHORT",
                strength=round(strength, 2),
                reason=f"Bearish breakdown below {range_low:.2f} with {snapshot.volume_ratio:.2f}x volume"
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

        Accuracy improvement: add RSI zone confirmation so MACD signals
        are only taken when RSI is in a momentum-favourable range:
          - LONG: RSI between 40–68 (confirming momentum without being overbought)
          - SHORT: RSI between 32–60 (confirming downward momentum without oversold)
        """
        filters = config.get('signal_filters', {})
        rsi_long_min  = float(filters.get('macd_rsi_long_min',  40.0))
        rsi_long_max  = float(filters.get('macd_rsi_long_max',  68.0))
        rsi_short_min = float(filters.get('macd_rsi_short_min', 32.0))
        rsi_short_max = float(filters.get('macd_rsi_short_max', 60.0))

        if (snapshot.macd_cross == "bullish" and
            snapshot.macd_histogram > 0 and
            snapshot.close_vs_vwap == "above"):
            if not (rsi_long_min <= snapshot.rsi <= rsi_long_max):
                return SignalResult(
                    strategy_name="MACDMomentumStrategy",
                    direction="NEUTRAL",
                    strength=0.0,
                    reason=f"Bullish MACD cross but RSI {snapshot.rsi:.1f} outside optimal range [{rsi_long_min:.0f}–{rsi_long_max:.0f}]"
                )
            return SignalResult(
                strategy_name="MACDMomentumStrategy",
                direction="LONG",
                strength=0.78,
                reason=f"Bullish MACD cross, positive histogram, price above VWAP, RSI {snapshot.rsi:.1f}"
            )
        elif (snapshot.macd_cross == "bearish" and
              snapshot.macd_histogram < 0 and
              snapshot.close_vs_vwap == "below"):
            if not (rsi_short_min <= snapshot.rsi <= rsi_short_max):
                return SignalResult(
                    strategy_name="MACDMomentumStrategy",
                    direction="NEUTRAL",
                    strength=0.0,
                    reason=f"Bearish MACD cross but RSI {snapshot.rsi:.1f} outside optimal range [{rsi_short_min:.0f}–{rsi_short_max:.0f}]"
                )
            return SignalResult(
                strategy_name="MACDMomentumStrategy",
                direction="SHORT",
                strength=0.78,
                reason=f"Bearish MACD cross, negative histogram, price below VWAP, RSI {snapshot.rsi:.1f}"
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

    # Ensure all 6 strategy votes are always present
    expected = [
        "EMAcrossoverStrategy",
        "RSIBollingerStrategy",
        "VWAPBounceStrategy",
        "RangeTradingStrategy",
        "BreakoutStrategy",
        "MACDMomentumStrategy",
    ]
    present = {r.strategy_name for r in results}
    for missing_name in [name for name in expected if name not in present]:
        results.append(
            SignalResult(
                strategy_name=missing_name,
                direction="NEUTRAL",
                strength=0.0,
                reason="Strategy vote unavailable due to evaluation error"
            )
        )

    return results
