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
        stop_pct    = risk_cfg.get('default_stop_loss_pct', 0.002)

        # ── Filter settings ───────────────────────────────────────────────────
        use_trend_filter = config.get('useTrendFilter', False)
        use_volume_filter = config.get('useVolumeFilter', False)
        vol_multiplier   = float(config.get('volMultiplier', 1.2))
        use_htf_bias     = config.get('useHtfBias', False)
        htf_ema_period   = int(config.get('htfEmaPeriod', 100))   # ~15m EMA-7 equivalent on 1m

        # ── Indicators (vectorized) ───────────────────────────────────────────
        data['ema_fast'] = data['close'].ewm(span=ema_fast_p, adjust=False).mean()
        data['ema_slow'] = data['close'].ewm(span=ema_slow_p, adjust=False).mean()

        delta = data['close'].diff()
        gain  = delta.where(delta > 0, 0.0).rolling(window=rsi_p).mean()
        loss  = (-delta.where(delta < 0, 0.0)).rolling(window=rsi_p).mean()
        data['rsi'] = 100 - (100 / (1 + (gain / loss.replace(0, np.nan)))).fillna(50)

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

        # ── Strategy Votes ────────────────────────────────────────────────────
        # s1: EMA Alignment (State-based for consensus)
        s1 = pd.Series(0, index=data.index)
        s1[data['ema_fast'] > data['ema_slow']] =  1
        s1[data['ema_fast'] < data['ema_slow']] = -1

        s2 = pd.Series(0, index=data.index)
        s2[(data['rsi'] < 30) & (data['close'] < data['bb_lo'])] =  1
        s2[(data['rsi'] > 70) & (data['close'] > data['bb_up'])] = -1

        s3 = pd.Series(0, index=data.index)
        s3[(data['close'] > data['vwap']) & (data['vol_ratio'] > 1.2)] =  1
        s3[(data['close'] < data['vwap']) & (data['vol_ratio'] > 1.2)] = -1

        s4 = pd.Series(0, index=data.index)
        ranging = data['range_pct'] <= 1.5
        near_lo  = (data['close'] - data['roll_lo']).abs() / data['roll_lo'].replace(0, np.nan) < 0.001
        near_hi  = (data['close'] - data['roll_high']).abs() / data['roll_high'].replace(0, np.nan) < 0.001
        s4[ranging & near_lo  & (data['rsi'] < 45)] =  1
        s4[ranging & near_hi  & (data['rsi'] > 55)] = -1

        s5 = pd.Series(0, index=data.index)
        s5[(data['close'] > data['roll_high'] * 1.002) & (data['vol_ratio'] > 1.5)] =  1
        s5[(data['close'] < data['roll_lo']   * 0.998) & (data['vol_ratio'] > 1.5)] = -1

        # s6: MACD Alignment (State-based for consensus)
        s6 = pd.Series(0, index=data.index)
        s6[data['macd_hist'] > 0] =  1
        s6[data['macd_hist'] < 0] = -1

        votes = pd.DataFrame({'s1': s1, 's2': s2, 's3': s3, 's4': s4, 's5': s5, 's6': s6})
        data['long_votes']  = (votes == 1).sum(axis=1)
        data['short_votes'] = (votes == -1).sum(axis=1)

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
        def get_agreeing(row_votes, direction):
            return [
                strategy_names[i]
                for i, sc in enumerate(s_cols)
                if (direction == "LONG"  and row_votes[sc] == 1) or
                   (direction == "SHORT" and row_votes[sc] == -1)
            ]

        signals: List[Dict[str, Any]] = []
        position     = None   # None, "LONG", "SHORT"
        entry_price  = 0.0
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

            # ── Check for exit / reversal ─────────────────────────────────────
            if position == "LONG" and sv >= min_exit_votes:
                # Exit the LONG
                signals[-1]['exitTimestamp'] = make_iso(ts)
                signals[-1]['exitPrice']     = close
                signals[-1]['exitType']      = 'signal'
                position = None

                # Immediately try to enter SHORT on this same candle (if filters pass)
                if sv >= min_votes and short_ok:
                    agreeing = get_agreeing(votes.iloc[idx], "SHORT")
                    iso_ts   = make_iso(ts)
                    signals.append({
                        "timestamp":       iso_ts,
                        "direction":       "SHORT",
                        "price":           close,
                        "votes":           f"{sv}/6",
                        "strategies":      "; ".join(agreeing),
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
                continue  # Move to next candle after exit

            elif position == "SHORT" and lv >= min_exit_votes:
                # Exit the SHORT
                signals[-1]['exitTimestamp'] = make_iso(ts)
                signals[-1]['exitPrice']     = close
                signals[-1]['exitType']      = 'signal'
                position = None

                # Immediately try to enter LONG on this same candle (if filters pass)
                if lv >= min_votes and long_ok:
                    agreeing = get_agreeing(votes.iloc[idx], "LONG")
                    iso_ts   = make_iso(ts)
                    signals.append({
                        "timestamp":       iso_ts,
                        "direction":       "LONG",
                        "price":           close,
                        "votes":           f"{lv}/6",
                        "strategies":      "; ".join(agreeing),
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
                continue

            # ── Open a new position if flat ───────────────────────────────────
            if position is None:
                if lv >= min_votes and long_ok:
                    direction = "LONG"
                elif sv >= min_votes and short_ok:
                    direction = "SHORT"
                else:
                    continue  # flat and no valid signal

                agreeing = get_agreeing(votes.iloc[idx], direction)
                iso_ts   = make_iso(ts)
                signals.append({
                    "timestamp":       iso_ts,
                    "direction":       direction,
                    "price":           close,
                    "votes":           f"{lv if direction == 'LONG' else sv}/6",
                    "strategies":      "; ".join(agreeing),
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

        # Mark last open trade as "open" (already set, no change needed)
        logger.info(f"Backtest complete: {len(signals)} trades in {len(data)} candles (position-based exits)")
        return signals

    except Exception as e:
        logger.error(f"Backtester error: {e}", exc_info=True)
        return []
