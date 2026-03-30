"""
Backtester Module - scanner/backtester.py

Provides high-performance vectorized signal detection for historical data.
Replicates the logic from strategies.py and indicators.py using pandas for efficiency.
"""

import pandas as pd
import numpy as np
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def run_backtest(df: pd.DataFrame, config: dict) -> List[Dict[str, Any]]:
    """
    Run all strategies on the provided historical DataFrame and return list of signals.
    
    Args:
        df: DataFrame with columns [time, open, high, low, close, volume]
        config: Configuration dictionary with strategy parameters
        
    Returns:
        List of signal objects ordered oldest → newest, compatible with frontend format.
    """
    if df.empty or len(df) < 50:
        return []

    try:
        data = df.copy().reset_index(drop=True)

        # ── Config ───────────────────────────────────────────────────────────
        ind_cfg = config.get('indicators', {})
        ema_fast_p  = ind_cfg.get('ema_fast', 9)
        ema_slow_p  = ind_cfg.get('ema_slow', 21)
        rsi_p       = ind_cfg.get('rsi_period', 14)
        macd_f      = ind_cfg.get('macd_fast', 12)
        macd_s      = ind_cfg.get('macd_slow', 26)
        macd_sig    = ind_cfg.get('macd_signal', 9)
        bb_p        = ind_cfg.get('bb_period', 20)
        bb_std_mult = ind_cfg.get('bb_std', 2)
        risk_cfg    = config.get('risk', {})
        min_votes   = config.get('min_votes', 3)
        target_rr   = risk_cfg.get('target_rr', 1.5)
        use_ts      = risk_cfg.get('useTrailingStop', False)
        ts_atr      = risk_cfg.get('trailingStopAtr', 2.0)
        use_fs      = risk_cfg.get('useFixedRiskReward', False)
        fs_sl       = risk_cfg.get('fixedStopLossPct', 1.0) / 100.0
        fs_tp       = risk_cfg.get('fixedTakeProfitPct', 2.0) / 100.0

        # ── Filter settings ───────────────────────────────────────────────────
        use_trend_filter = config.get('useTrendFilter', False)
        use_volume_filter = config.get('useVolumeFilter', False)
        vol_multiplier   = float(config.get('volMultiplier', 1.2))
        use_htf_bias     = config.get('useHtfBias', False)
        htf_ema_period   = int(config.get('htfEmaPeriod', 100))   # ~15m EMA-7 equivalent on 1m
        signal_filters = config.get('signal_filters', {})
        min_ema_spread_pct = float(signal_filters.get('min_ema_spread_pct', 0.0005))
        require_rsi_ema_alignment = bool(signal_filters.get('require_rsi_ema_alignment', True))
        rsi_ema_alignment_tolerance = float(signal_filters.get('rsi_ema_alignment_tolerance', 0.002))
        vwap_crossover_only = bool(signal_filters.get('vwap_crossover_only', True))
        vwap_vol_threshold = float(signal_filters.get('vwap_vol_threshold', 1.2))
        breakout_vol_threshold = float(signal_filters.get('breakout_vol_threshold', 1.5))
        macd_rsi_long_min = float(signal_filters.get('macd_rsi_long_min', 40.0))
        macd_rsi_long_max = float(signal_filters.get('macd_rsi_long_max', 68.0))
        macd_rsi_short_min = float(signal_filters.get('macd_rsi_short_min', 32.0))
        macd_rsi_short_max = float(signal_filters.get('macd_rsi_short_max', 60.0))
        min_signal_strength = float(signal_filters.get('min_signal_strength', 0.0))

        # ── Indicators (vectorized) ───────────────────────────────────────────
        data['ema_fast'] = data['close'].ewm(span=ema_fast_p, adjust=False).mean()
        data['ema_slow'] = data['close'].ewm(span=ema_slow_p, adjust=False).mean()

        delta = data['close'].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta.where(delta < 0, 0.0))
        alpha = 1.0 / max(1, rsi_p)
        avg_gain = gain.ewm(alpha=alpha, adjust=False).mean()
        avg_loss = loss.ewm(alpha=alpha, adjust=False).mean()
        data['rsi'] = 50.0
        normal = avg_loss > 0
        rs = avg_gain[normal] / avg_loss[normal]
        data.loc[normal, 'rsi'] = 100.0 - (100.0 / (1.0 + rs))
        data.loc[(avg_loss == 0) & (avg_gain > 0), 'rsi'] = 100.0

        ema_f_macd      = data['close'].ewm(span=macd_f, adjust=False).mean()
        ema_s_macd      = data['close'].ewm(span=macd_s, adjust=False).mean()
        data['macd_line']   = ema_f_macd - ema_s_macd
        data['macd_signal'] = data['macd_line'].ewm(span=macd_sig, adjust=False).mean()
        data['macd_hist']   = data['macd_line'] - data['macd_signal']

        data['bb_mid'] = data['close'].rolling(window=bb_p).mean()
        bb_std         = data['close'].rolling(window=bb_p).std()
        data['bb_up']  = data['bb_mid'] + (bb_std * bb_std_mult)
        data['bb_lo']  = data['bb_mid'] - (bb_std * bb_std_mult)

        # VWAP resets at each UTC day boundary (realistic)
        typical_price = (data['high'] + data['low'] + data['close']) / 3
        if pd.api.types.is_datetime64_any_dtype(data['time']):
            data['_day'] = data['time'].dt.date
        else:
            data['_day'] = pd.to_datetime(data['time'], utc=True).dt.date
        data['_cum_pv']  = (typical_price * data['volume']).groupby(data['_day']).cumsum()
        data['_cum_vol'] = data['volume'].groupby(data['_day']).cumsum()
        data['vwap'] = data['_cum_pv'] / data['_cum_vol'].replace(0, np.nan)
        data['vwap'] = data['vwap'].ffill().fillna(data['close'])

        data['vol_avg']   = data['volume'].rolling(window=20).mean()
        data['vol_ratio'] = (data['volume'] / data['vol_avg'].replace(0, np.nan)).fillna(1.0)

        data['roll_high'] = data['high'].rolling(window=20).max()
        data['roll_lo']   = data['low'].rolling(window=20).min()
        data['range_pct'] = ((data['roll_high'] - data['roll_lo']) / data['roll_lo'].replace(0, np.nan)) * 100
        data['prev_roll_high'] = data['high'].rolling(window=20).max().shift(1)
        data['prev_roll_lo'] = data['low'].rolling(window=20).min().shift(1)

        data['ema_spread_pct'] = ((data['ema_fast'] - data['ema_slow']).abs() / data['ema_slow'].replace(0, np.nan)).fillna(0.0)
        data['close_vs_vwap'] = np.where(data['close'] > data['vwap'], 'above', 'below')
        data['prev_close_vs_vwap'] = data['close_vs_vwap'].shift(1).fillna(data['close_vs_vwap'])
        data['macd_hist_prev'] = data['macd_hist'].shift(1)
        data['macd_cross'] = 'none'
        data.loc[(data['macd_hist_prev'] <= 0) & (data['macd_hist'] > 0), 'macd_cross'] = 'bullish'
        data.loc[(data['macd_hist_prev'] >= 0) & (data['macd_hist'] < 0), 'macd_cross'] = 'bearish'

        # ATR Calculation for Trailing Stops
        data['tr0'] = abs(data['high'] - data['low'])
        data['tr1'] = abs(data['high'] - data['close'].shift())
        data['tr2'] = abs(data['low'] - data['close'].shift())
        data['tr'] = data[['tr0', 'tr1', 'tr2']].max(axis=1)
        data['atr'] = data['tr'].rolling(window=14).mean().bfill()

        # ── Strategy Votes (aligned with live scanner logic) ─────────────────
        s1 = pd.Series(0, index=data.index)
        s1_strength = pd.Series(0.0, index=data.index)
        ema_bull_cross = (data['ema_fast'].shift(1) <= data['ema_slow'].shift(1)) & (data['ema_fast'] > data['ema_slow'])
        ema_bear_cross = (data['ema_fast'].shift(1) >= data['ema_slow'].shift(1)) & (data['ema_fast'] < data['ema_slow'])
        spread_ok = data['ema_spread_pct'] >= min_ema_spread_pct
        s1[ema_bull_cross & spread_ok] = 1
        s1[ema_bear_cross & spread_ok] = -1
        s1_strength[s1 != 0] = (0.60 + data.loc[s1 != 0, 'ema_spread_pct'] * 50).clip(upper=0.95)

        s2 = pd.Series(0, index=data.index)
        s2_strength = pd.Series(0.0, index=data.index)
        s2_long = (data['rsi'] < 30) & (data['close'] < data['bb_lo'])
        s2_short = (data['rsi'] > 70) & (data['close'] > data['bb_up'])
        if require_rsi_ema_alignment:
            s2_long = s2_long & (data['ema_fast'] >= data['ema_slow'] * (1.0 - rsi_ema_alignment_tolerance))
            s2_short = s2_short & (data['ema_fast'] <= data['ema_slow'] * (1.0 + rsi_ema_alignment_tolerance))
        s2[s2_long] = 1
        s2[s2_short] = -1
        s2_strength[s2 != 0] = 0.80

        s3 = pd.Series(0, index=data.index)
        s3_strength = pd.Series(0.0, index=data.index)
        vol_ok_vwap = data['vol_ratio'] > vwap_vol_threshold
        if vwap_crossover_only:
            crossed_above = (data['prev_close_vs_vwap'] == 'below') & (data['close_vs_vwap'] == 'above')
            crossed_below = (data['prev_close_vs_vwap'] == 'above') & (data['close_vs_vwap'] == 'below')
            s3[crossed_above & vol_ok_vwap] = 1
            s3[crossed_below & vol_ok_vwap] = -1
        else:
            s3[(data['close_vs_vwap'] == 'above') & vol_ok_vwap] = 1
            s3[(data['close_vs_vwap'] == 'below') & vol_ok_vwap] = -1
        s3_strength[s3 != 0] = (0.60 + (data.loc[s3 != 0, 'vol_ratio'] - 1.0) * 0.15).clip(upper=0.90)

        s4 = pd.Series(0, index=data.index)
        s4_strength = pd.Series(0.0, index=data.index)
        ranging = data['range_pct'] <= 1.5
        near_lo = (data['close'] - data['roll_lo']).abs() / data['roll_lo'].replace(0, np.nan) < 0.001
        near_hi = (data['close'] - data['roll_high']).abs() / data['roll_high'].replace(0, np.nan) < 0.001
        s4[ranging & near_lo & (data['rsi'] < 45)] = 1
        s4[ranging & near_hi & (data['rsi'] > 55)] = -1
        s4_strength[s4 != 0] = 0.65

        s5 = pd.Series(0, index=data.index)
        s5_strength = pd.Series(0.0, index=data.index)
        breakout_long = (data['close'] > data['prev_roll_high'] * 1.002) & (data['vol_ratio'] > breakout_vol_threshold)
        breakout_short = (data['close'] < data['prev_roll_lo'] * 0.998) & (data['vol_ratio'] > breakout_vol_threshold)
        s5[breakout_long] = 1
        s5[breakout_short] = -1
        s5_long_excess = ((data['close'] - data['prev_roll_high']) / data['prev_roll_high'].replace(0, np.nan)).fillna(0.0)
        s5_short_excess = ((data['prev_roll_lo'] - data['close']) / data['prev_roll_lo'].replace(0, np.nan)).fillna(0.0)
        s5_strength[breakout_long] = (0.75 + (s5_long_excess[breakout_long] * 10) + ((data.loc[breakout_long, 'vol_ratio'] - 1.5) * 0.05)).clip(upper=0.95)
        s5_strength[breakout_short] = (0.75 + (s5_short_excess[breakout_short] * 10) + ((data.loc[breakout_short, 'vol_ratio'] - 1.5) * 0.05)).clip(upper=0.95)

        s6 = pd.Series(0, index=data.index)
        s6_strength = pd.Series(0.0, index=data.index)
        s6_long = (
            (data['macd_cross'] == 'bullish') &
            (data['macd_hist'] > 0) &
            (data['close_vs_vwap'] == 'above') &
            (data['rsi'] >= macd_rsi_long_min) &
            (data['rsi'] <= macd_rsi_long_max)
        )
        s6_short = (
            (data['macd_cross'] == 'bearish') &
            (data['macd_hist'] < 0) &
            (data['close_vs_vwap'] == 'below') &
            (data['rsi'] >= macd_rsi_short_min) &
            (data['rsi'] <= macd_rsi_short_max)
        )
        s6[s6_long] = 1
        s6[s6_short] = -1
        s6_strength[s6 != 0] = 0.78

        votes = pd.DataFrame({'s1': s1, 's2': s2, 's3': s3, 's4': s4, 's5': s5, 's6': s6})
        strengths = pd.DataFrame({
            's1': s1_strength, 's2': s2_strength, 's3': s3_strength,
            's4': s4_strength, 's5': s5_strength, 's6': s6_strength
        }).fillna(0.0)
        qualified_votes = votes.where(strengths >= min_signal_strength, 0)

        data['long_votes'] = (qualified_votes == 1).sum(axis=1)
        data['short_votes'] = (qualified_votes == -1).sum(axis=1)

        # ── Compute Filters (vectorized) ──────────────────────────────────────
        # 1. Trend Filter: EMA-fast must align with direction
        data['trend_long_ok']  = data['ema_fast'] > data['ema_slow']
        data['trend_short_ok'] = data['ema_fast'] < data['ema_slow']

        # 2. Volume Confirmation: current volume >= vol_multiplier × 20-bar average
        vol_mean_20 = data['volume'].rolling(window=20).mean()
        # Prevent division by zero - use a small epsilon for comparison
        vol_mean_20_safe = vol_mean_20.replace(0, np.nan).fillna(1e-8)
        data['volume_ok'] = data['volume'] >= (vol_mean_20_safe * vol_multiplier)

        # 3. Higher Timeframe Bias: close vs long-period EMA (approximates 15m trend)
        data['htf_ema']       = data['close'].ewm(span=htf_ema_period, adjust=False).mean()
        data['htf_long_ok']   = data['close'] > data['htf_ema']
        data['htf_short_ok']  = data['close'] < data['htf_ema']

        # ── Position State Machine ────────────────────────────────────────────
        # Rules:
        #   1. Only one trade open at a time.
        #   2. Enter on any candle where long_votes >= min_votes (and flat).
        #   3. Exit a LONG when short_votes >= min_exit_votes (opposite consensus).
        #   4. Enter the opposite position on the same candle that triggers exit (flip).
        #   5. No fixed TP/SL — the algorithm decides when to exit.

        min_exit_votes = max(1, config.get('min_exit_votes', min_votes - 1))
        strategy_names = [
            "EMAcrossoverStrategy", "RSIBollingerStrategy", "VWAPBounceStrategy",
            "RangeTradingStrategy", "BreakoutStrategy", "MACDMomentumStrategy"
        ]
        s_cols = ['s1', 's2', 's3', 's4', 's5', 's6']

        # Helper: get strategies that agree with a direction at given row
        def get_agreeing(row_votes, row_strengths, direction):
            agreeing = []
            for i, sc in enumerate(s_cols):
                strength_ok = row_strengths[sc] >= min_signal_strength
                if direction == "LONG" and row_votes[sc] == 1 and strength_ok:
                    agreeing.append(strategy_names[i])
                elif direction == "SHORT" and row_votes[sc] == -1 and strength_ok:
                    agreeing.append(strategy_names[i])
            return agreeing

        signals: List[Dict[str, Any]] = []
        position     = None   # None, "LONG", "SHORT"
        entry_price  = 0.0
        peak_price   = 0.0    # Tracks highest/lowest price for trailing stops
        entry_ts     = None
        entry_idx    = -1
        entry_votes_str = ""
        entry_agreeing  = []

        def make_iso(ts):
            return ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)

        for idx in range(len(data)):
            row   = data.iloc[idx]
            lv    = int(row['long_votes'])
            sv    = int(row['short_votes'])
            close = float(row['close'])
            ts    = row['time']

            # ── Per-candle filter checks ──────────────────────────────────────
            long_ok  = (
                (not use_trend_filter  or bool(row['trend_long_ok'])) and
                (not use_volume_filter or bool(row['volume_ok'])) and
                (not use_htf_bias      or bool(row['htf_long_ok']))
            )
            short_ok = (
                (not use_trend_filter  or bool(row['trend_short_ok'])) and
                (not use_volume_filter or bool(row['volume_ok'])) and
                (not use_htf_bias      or bool(row['htf_short_ok']))
            )

            # ── Check for hard TP/SL or Trailing Stop Hit ─────────────────────
            if position == "LONG":
                peak_price = max(peak_price, float(row['high']))
                atr = float(row['atr'])
                ts_price = peak_price - (atr * ts_atr)
                sl_price = entry_price * (1 - fs_sl)
                tp_price = entry_price * (1 + fs_tp)

                exit_reason = None
                exit_price = None

                if use_fs and float(row['low']) <= sl_price:
                    exit_reason = 'stoploss'
                    exit_price = sl_price
                elif use_fs and float(row['high']) >= tp_price:
                    exit_reason = 'target'
                    exit_price = tp_price
                elif use_ts and float(row['low']) <= ts_price:
                    exit_reason = 'trailing_stop'
                    exit_price = ts_price

                if exit_reason:
                    signals[-1]['exitTimestamp'] = make_iso(ts)
                    signals[-1]['exitPrice']     = exit_price
                    signals[-1]['exitType']      = exit_reason
                    position = None
                    continue

            elif position == "SHORT":
                peak_price = min(peak_price, float(row['low']))
                atr = float(row['atr'])
                ts_price = peak_price + (atr * ts_atr)
                sl_price = entry_price * (1 + fs_sl)
                tp_price = entry_price * (1 - fs_tp)

                exit_reason = None
                exit_price = None

                if use_fs and float(row['high']) >= sl_price:
                    exit_reason = 'stoploss'
                    exit_price = sl_price
                elif use_fs and float(row['low']) <= tp_price:
                    exit_reason = 'target'
                    exit_price = tp_price
                elif use_ts and float(row['high']) >= ts_price:
                    exit_reason = 'trailing_stop'
                    exit_price = ts_price

                if exit_reason:
                    signals[-1]['exitTimestamp'] = make_iso(ts)
                    signals[-1]['exitPrice']     = exit_price
                    signals[-1]['exitType']      = exit_reason
                    position = None
                    continue

            # ── Check for standard reversal logic ─────────────────────────────
            if position == "LONG" and sv >= min_exit_votes:
                # Exit the LONG
                signals[-1]['exitTimestamp'] = make_iso(ts)
                signals[-1]['exitPrice']     = close
                signals[-1]['exitType']      = 'signal'
                position = None

                # Immediately try to enter SHORT on this same candle (if filters pass)
                if sv >= min_votes and short_ok and sv > lv:
                    agreeing = get_agreeing(votes.iloc[idx], strengths.iloc[idx], "SHORT")
                    iso_ts   = make_iso(ts)
                    signals.append({
                        "timestamp":       iso_ts,
                        "direction":       "SHORT",
                        "price":           close,
                        "votes":           f"{sv}/6",
                        "strategies":      "; ".join(agreeing),
                        "agreeingStrategies": agreeing,
                        "avgStrength":     round(len(agreeing) / 6, 2),
                        "interval":        "history",
                        "entry":           close,
                        "stopLoss":        None,
                        "target":          None,
                        "targetRr":        None,
                        "entryTimestamp":  iso_ts,
                        "entryDirection":  "SHORT",
                        "exitTimestamp":   None,
                        "exitPrice":       None,
                        "exitType":        "open",
                    })
                    position = "SHORT"
                    entry_price = close
                    peak_price = close
                continue  # Move to next candle after exit

            elif position == "SHORT" and lv >= min_exit_votes:
                # Exit the SHORT
                signals[-1]['exitTimestamp'] = make_iso(ts)
                signals[-1]['exitPrice']     = close
                signals[-1]['exitType']      = 'signal'
                position = None

                # Immediately try to enter LONG on this same candle (if filters pass)
                if lv >= min_votes and long_ok and lv > sv:
                    agreeing = get_agreeing(votes.iloc[idx], strengths.iloc[idx], "LONG")
                    iso_ts   = make_iso(ts)
                    signals.append({
                        "timestamp":       iso_ts,
                        "direction":       "LONG",
                        "price":           close,
                        "votes":           f"{lv}/6",
                        "strategies":      "; ".join(agreeing),
                        "agreeingStrategies": agreeing,
                        "avgStrength":     round(len(agreeing) / 6, 2),
                        "interval":        "history",
                        "entry":           close,
                        "stopLoss":        None,
                        "target":          None,
                        "targetRr":        None,
                        "entryTimestamp":  iso_ts,
                        "entryDirection":  "LONG",
                        "exitTimestamp":   None,
                        "exitPrice":       None,
                        "exitType":        "open",
                    })
                    position = "LONG"
                    entry_price = close
                    peak_price = close
                continue

            # ── Open a new position if flat ───────────────────────────────────
            if position is None:
                if lv >= min_votes and long_ok and lv > sv:
                    direction = "LONG"
                elif sv >= min_votes and short_ok and sv > lv:
                    direction = "SHORT"
                else:
                    continue  # flat and no valid signal

                agreeing = get_agreeing(votes.iloc[idx], strengths.iloc[idx], direction)
                iso_ts   = make_iso(ts)
                signals.append({
                    "timestamp":       iso_ts,
                    "direction":       direction,
                    "price":           close,
                    "votes":           f"{lv if direction == 'LONG' else sv}/6",
                    "strategies":      "; ".join(agreeing),
                    "agreeingStrategies": agreeing,
                    "avgStrength":     round(len(agreeing) / 6, 2),
                    "interval":        "history",
                    "entry":           close,
                    "stopLoss":        None,
                    "target":          None,
                    "targetRr":        None,
                    "entryTimestamp":  iso_ts,
                    "entryDirection":  direction,
                    "exitTimestamp":   None,
                    "exitPrice":       None,
                    "exitType":        "open",
                })
                position = direction
                entry_price = close
                peak_price = close

        # Mark last open trade as "open" (already set, no change needed)
        logger.info(f"Backtest complete: {len(signals)} trades in {len(data)} candles (position-based exits)")
        return signals

    except Exception as e:
        logger.error(f"Backtester error: {e}", exc_info=True)
        return []
