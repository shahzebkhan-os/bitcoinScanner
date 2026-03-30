"""
REST API Routes Module - api/rest_routes.py

Responsibilities:
- Provide REST endpoints for config and history
- Health check endpoint
- CORS configuration
"""

import logging
import csv
import os
import itertools
import math
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yaml
from typing import Optional
from scanner.backtester import run_backtest
import numpy as np

logger = logging.getLogger(__name__)
DEFAULT_STOP_LOSS_PCT = 0.002


def _snake_to_camel(key: str) -> str:
    parts = key.split("_")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def _camelize(data):
    if isinstance(data, list):
        return [_camelize(item) for item in data]
    if isinstance(data, dict):
        return {_snake_to_camel(str(k)): _camelize(v) for k, v in data.items()}
    return data


def _build_backtest_config(body: dict, config: dict) -> dict:
    min_votes = int(body.get("minVotes", config.get("min_votes", 3)))
    min_exit_votes = int(body.get("minExitVotes", max(1, min_votes - 1)))

    return {
        "min_votes": min_votes,
        "min_exit_votes": min_exit_votes,
        "enabled_strategies": body.get("enabledStrategies", config.get("enabled_strategies", [])),
        "useTrendFilter": bool(body.get("useTrendFilter", False)),
        "useVolumeFilter": bool(body.get("useVolumeFilter", False)),
        "volMultiplier": float(body.get("volMultiplier", 1.2)),
        "useHtfBias": bool(body.get("useHtfBias", False)),
        "htfEmaPeriod": int(body.get("htfEmaPeriod", 100)),
        "risk": {
            "useTrailingStop": bool(body.get("useTrailingStop", False)),
            "trailingStopAtr": float(body.get("trailingStopAtr", 2.0)),
            "useFixedRiskReward": bool(body.get("useFixedRiskReward", False)),
            "fixedStopLossPct": float(body.get("fixedStopLossPct", 1.0)),
            "fixedTakeProfitPct": float(body.get("fixedTakeProfitPct", 2.0)),
            "target_rr": 1.5,
            "default_stop_loss_pct": 0.002,
        },
        "indicators": {
            "ema_fast": int(body.get("emaFast", 9)),
            "ema_slow": int(body.get("emaSlow", 21)),
            "rsi_period": int(body.get("rsiPeriod", 14)),
            "rsi_oversold": float(body.get("rsiOversold", 30)),
            "rsi_overbought": float(body.get("rsiOverbought", 70)),
            "macd_fast": int(body.get("macdFast", 12)),
            "macd_slow": int(body.get("macdSlow", 26)),
            "macd_signal": int(body.get("macdSignal", 9)),
            "bb_period": int(body.get("bbPeriod", 20)),
            "bb_std": float(body.get("bbStd", 2)),
        },
        "signal_filters": {
            "min_ema_spread_pct": float(body.get(
                "minEmaSpreadPct",
                config.get("signal_filters", {}).get("min_ema_spread_pct", 0.0005),
            )),
            "require_rsi_ema_alignment": bool(body.get(
                "requireRsiEmaAlignment",
                config.get("signal_filters", {}).get("require_rsi_ema_alignment", True),
            )),
            "rsi_ema_alignment_tolerance": float(body.get(
                "rsiEmaAlignmentTolerance",
                config.get("signal_filters", {}).get("rsi_ema_alignment_tolerance", 0.002),
            )),
            "vwap_crossover_only": bool(body.get(
                "vwapCrossoverOnly",
                config.get("signal_filters", {}).get("vwap_crossover_only", True),
            )),
            "vwap_vol_threshold": float(body.get(
                "vwapVolThreshold",
                config.get("signal_filters", {}).get("vwap_vol_threshold", 1.2),
            )),
            "breakout_vol_threshold": float(body.get(
                "breakoutVolThreshold",
                config.get("signal_filters", {}).get("breakout_vol_threshold", 1.5),
            )),
            "macd_rsi_long_min": float(body.get(
                "macdRsiLongMin",
                config.get("signal_filters", {}).get("macd_rsi_long_min", 40.0),
            )),
            "macd_rsi_long_max": float(body.get(
                "macdRsiLongMax",
                config.get("signal_filters", {}).get("macd_rsi_long_max", 68.0),
            )),
            "macd_rsi_short_min": float(body.get(
                "macdRsiShortMin",
                config.get("signal_filters", {}).get("macd_rsi_short_min", 32.0),
            )),
            "macd_rsi_short_max": float(body.get(
                "macdRsiShortMax",
                config.get("signal_filters", {}).get("macd_rsi_short_max", 60.0),
            )),
            "min_signal_strength": float(body.get(
                "minSignalStrength",
                config.get("signal_filters", {}).get("min_signal_strength", 0.0),
            )),
            "ml_long_threshold": float(body.get(
                "mlLongThreshold",
                config.get("signal_filters", {}).get("ml_long_threshold", 0.60),
            )),
            "ml_short_threshold": float(body.get(
                "mlShortThreshold",
                config.get("signal_filters", {}).get("ml_short_threshold", 0.40),
            )),
            "ml_weight_ema_bias": float(body.get(
                "mlWeightEmaBias",
                config.get("signal_filters", {}).get("ml_weight_ema_bias", 0.65),
            )),
            "ml_weight_macd_sign": float(body.get(
                "mlWeightMacdSign",
                config.get("signal_filters", {}).get("ml_weight_macd_sign", 0.55),
            )),
            "ml_weight_vwap_bias": float(body.get(
                "mlWeightVwapBias",
                config.get("signal_filters", {}).get("ml_weight_vwap_bias", 0.45),
            )),
            "ml_weight_rsi_norm": float(body.get(
                "mlWeightRsiNorm",
                config.get("signal_filters", {}).get("ml_weight_rsi_norm", 0.40),
            )),
            "ml_weight_volume_bias": float(body.get(
                "mlWeightVolumeBias",
                config.get("signal_filters", {}).get("ml_weight_volume_bias", 0.30),
            )),
        },
    }


def _compute_sweep_metrics(signals: list, initial_capital: float, trade_size_pct: float, trade_amount: float) -> dict:
    """
    Compute compact ranking metrics for a sweep result from backtest signals.

    Args:
        signals: Backtester trade/signal list.
        initial_capital: Starting capital for simulated compounding.
        trade_size_pct: Fraction of capital to deploy per trade when trade_amount is 0.
        trade_amount: Fixed dollar position size (overrides trade_size_pct when > 0).

    Returns:
        Dict with netReturnPct, maxDrawdown, sortinoRatio, closedTrades, and winRate.
    """
    capital = initial_capital
    peak_capital = initial_capital
    max_drawdown = 0.0
    returns_list = []
    closed_trades = 0
    wins = 0

    for s in signals:
        entry = s.get("entry")
        exit_p = s.get("exitPrice")
        if s.get("exitType") == "open" or exit_p is None or entry in (None, 0):
            continue

        trade_capital = trade_amount if trade_amount > 0 else capital * trade_size_pct
        pct_chg = (exit_p - entry) / entry if s.get("direction") == "LONG" else (entry - exit_p) / entry
        pnl = trade_capital * pct_chg
        capital += pnl
        closed_trades += 1
        if pnl > 0:
            wins += 1

        returns_list.append(pct_chg * 100)
        peak_capital = max(peak_capital, capital)
        if peak_capital > 0:
            drawdown = (peak_capital - capital) / peak_capital * 100
            max_drawdown = max(max_drawdown, drawdown)

    net_return_pct = ((capital - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0.0
    sortino_ratio = 0.0
    if len(returns_list) > 1:
        returns_arr = np.array(returns_list)
        mean_return = np.mean(returns_arr)
        downside_returns = returns_arr[returns_arr < 0]
        if len(downside_returns) > 0:
            downside_std = np.std(downside_returns)
            if downside_std > 0:
                sortino_ratio = mean_return / downside_std

    win_rate = (wins / closed_trades * 100) if closed_trades > 0 else 0.0
    return {
        "netReturnPct": round(net_return_pct, 2),
        "maxDrawdown": round(max_drawdown, 2),
        "sortinoRatio": round(sortino_ratio, 2),
        "closedTrades": closed_trades,
        "winRate": round(win_rate, 1),
    }


def setup_routes(app: FastAPI, config: dict, start_time: datetime, runtime_state: Optional[dict] = None):
    """
    Set up REST API routes.

    Args:
        app: FastAPI application instance
        config: Configuration dictionary
        start_time: Application start time
    """

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:4200", "http://localhost"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/config")
    async def get_config():
        """Return current configuration (sanitized)."""
        try:
            # Make a copy and sanitize
            sanitized = dict(config)
            if 'telegram' in sanitized:
                sanitized['telegram']['bot_token'] = "***REDACTED***"
            if 'risk' in sanitized:
                sanitized['risk'] = {
                    "maxLeverage": sanitized['risk'].get("max_leverage"),
                    "riskPerTradePct": sanitized['risk'].get("risk_per_trade_pct"),
                    "targetRr": sanitized['risk'].get("target_rr"),
                    "defaultStopLossPct": sanitized['risk'].get("default_stop_loss_pct", DEFAULT_STOP_LOSS_PCT),
                }
            return _camelize(sanitized)
        except Exception as e:
            logger.error(f"Error getting config: {e}")
            return {"error": str(e)}

    @app.get("/signals/history")
    async def get_signals_history(limit: int = 1000):
        """Return last N signals from CSV log."""
        try:
            csv_file = "signals_log.csv"

            if not os.path.isfile(csv_file):
                return {"signals": []}

            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            # Return last N rows
            signals = rows[-limit:] if len(rows) > limit else rows
            # Reverse to show newest first
            signals.reverse()

            camel_signals = []
            for row in signals:
                converted = {_snake_to_camel(k): v for k, v in row.items()}
                camel_signals.append(converted)
            return {"signals": camel_signals}

        except Exception as e:
            logger.error(f"Error reading signals history: {e}")
            return {"error": str(e)}

    @app.get("/candles/history")
    async def get_candles_history(pair: str = "BTCUSDT", interval: str = "1m", limit: int = 1000):
        """Return historical candles using pagination."""
        try:
            from scanner.fetcher import fetch_candles_paginated
            # Cap limit to 50k to prevent extreme resource usage
            safe_limit = min(50000, max(1, limit))
            df = await fetch_candles_paginated(pair, interval, safe_limit)
            
            if df is None or df.empty:
                return {"candles": []}
            
            # Format for frontend lightweight-charts
            result = []
            for _, row in df.iterrows():
                result.append({
                    'time': int(row['time'].timestamp() * 1000),
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': float(row['volume'])
                })
            # Run historical backtest
            historical_signals = run_backtest(df, config)

            return {
                "candles": result,
                "signals": historical_signals
            }
        except Exception as e:
            logger.error(f"Error fetching historical candles: {e}")
            return {"error": str(e)}

    @app.post("/backtest")
    async def run_backtest_endpoint(body: dict):
        """Run a parameterized backtest on historical data."""
        try:
            from scanner.fetcher import fetch_candles_paginated
            from scanner.backtester import run_backtest

            pair     = body.get("pair", "BTCUSDT")
            interval = body.get("interval", "1m")
            limit    = min(50000, max(100, int(body.get("limit", 1000))))

            custom_config = _build_backtest_config(body, config)

            df = await fetch_candles_paginated(pair, interval, limit)
            if df is None or df.empty:
                return {"candles": [], "signals": [], "stats": {}}

            candles_list = [
                {'time': int(row['time'].timestamp() * 1000),
                 'open': float(row['open']), 'high': float(row['high']),
                 'low': float(row['low']),  'close': float(row['close']),
                 'volume': float(row['volume'])}
                for _, row in df.iterrows()
            ]

            signals = run_backtest(df, custom_config)

            # ── Compute P&L Statistics ────────────────────────────────────────
            # With signal-based exits, a WIN = positive return (close > entry for LONG)
            initial_capital = float(body.get("initialCapital", 10000))
            trade_size_pct  = float(body.get("tradeSizePct", 0.1))   # fraction of capital
            trade_amount    = float(body.get("tradeAmount", 0))       # fixed $ per trade (0 = use %)

            total       = len(signals)
            open_trades = [s for s in signals if s.get("exitType") == "open"]

            # P&L tracking
            total_pnl    = 0.0
            total_profit = 0.0
            total_loss   = 0.0
            peak_capital = initial_capital
            capital      = initial_capital
            max_drawdown = 0.0
            wins_count   = 0
            losses_count = 0
            long_wins    = 0
            long_total   = 0
            short_wins   = 0
            short_total  = 0

            trade_rows = []
            equity_curve = [{"timestamp": signals[0]["timestamp"] if signals else "", "capital": initial_capital}]

            # Advanced metrics tracking
            returns_list = []  # For Sortino ratio
            win_streak = 0
            loss_streak = 0
            max_win_streak = 0
            max_loss_streak = 0
            current_streak_type = None  # "win" or "loss"
            strategy_perf = {}

            for s in signals:
                entry  = s["entry"]
                exit_p = s.get("exitPrice")

                # Determine trade size: fixed amount OR fraction of current capital
                if trade_amount > 0:
                    trade_capital = trade_amount
                else:
                    trade_capital = capital * trade_size_pct

                # Count direction totals
                if s["direction"] == "LONG":
                    long_total += 1
                else:
                    short_total += 1

                if s.get("exitType") != "open" and exit_p is not None:
                    pct_chg = (exit_p - entry) / entry if s["direction"] == "LONG" else (entry - exit_p) / entry
                    pnl     = trade_capital * pct_chg
                    capital += pnl
                    total_pnl += pnl

                    # Track return for Sortino ratio
                    returns_list.append(pct_chg * 100)  # Store as percentage

                    # Track equity curve on each trade close
                    if s.get("exitTimestamp"):
                        equity_curve.append({
                            "timestamp": s["exitTimestamp"],
                            "capital": round(capital, 2)
                        })

                    strat_key = s.get("strategies", "Unknown")
                    if strat_key not in strategy_perf:
                        strategy_perf[strat_key] = {"trades": 0, "wins": 0, "pnl": 0.0}
                    strategy_perf[strat_key]["trades"] += 1
                    strategy_perf[strat_key]["pnl"] += pnl

                    if pnl > 0:
                        total_profit += pnl
                        wins_count += 1
                        strategy_perf[strat_key]["wins"] += 1
                        if s["direction"] == "LONG": long_wins += 1
                        else: short_wins += 1
                        result_label = "WIN"

                        # Track win streak
                        if current_streak_type == "win":
                            win_streak += 1
                        else:
                            win_streak = 1
                            current_streak_type = "win"
                        max_win_streak = max(max_win_streak, win_streak)
                        loss_streak = 0
                    else:
                        total_loss += pnl   # negative number
                        losses_count += 1
                        result_label = "LOSS"

                        # Track loss streak
                        if current_streak_type == "loss":
                            loss_streak += 1
                        else:
                            loss_streak = 1
                            current_streak_type = "loss"
                        max_loss_streak = max(max_loss_streak, loss_streak)
                        win_streak = 0
                    if capital > peak_capital:
                        peak_capital = capital
                    drawdown = (peak_capital - capital) / peak_capital * 100
                    if drawdown > max_drawdown:
                        max_drawdown = drawdown
                else:
                    pnl = 0.0
                    result_label = "OPEN"

                trade_rows.append({
                    "timestamp":  s["timestamp"],
                    "direction":  s["direction"],
                    "entry":      round(entry, 2),
                    "exit":       round(exit_p or 0, 2),
                    "exitType":   s.get("exitType", "open"),
                    "exitPrice":  round(exit_p or 0, 2),
                    "pnl":        round(pnl, 2),
                    "result":     result_label,
                    "votes":      s["votes"],
                    "strategies": s.get("strategies", ""),
                })

            win_rate = (wins_count / total * 100) if total > 0 else 0

            # Calculate advanced risk metrics
            import numpy as np

            # Sortino Ratio: Similar to Sharpe but only penalizes downside volatility
            sortino_ratio = 0.0
            if len(returns_list) > 1:
                returns_arr = np.array(returns_list)
                mean_return = np.mean(returns_arr)
                downside_returns = returns_arr[returns_arr < 0]
                if len(downside_returns) > 0:
                    downside_std = np.std(downside_returns)
                    if downside_std > 0:
                        sortino_ratio = mean_return / downside_std

            # Calmar Ratio: Annual return / Max Drawdown
            calmar_ratio = 0.0
            total_return_pct = ((capital - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0
            if max_drawdown > 0:
                calmar_ratio = total_return_pct / max_drawdown

            # Average win/loss
            avg_win = (total_profit / wins_count) if wins_count > 0 else 0
            avg_loss = abs(total_loss / losses_count) if losses_count > 0 else 0
            profit_factor = (total_profit / abs(total_loss)) if total_loss != 0 else 0

            # Buy-and-hold benchmark
            buy_hold_return = 0.0
            buy_hold_final_capital = initial_capital
            if candles_list and len(candles_list) > 1:
                first_price = candles_list[0]['close']
                last_price = candles_list[-1]['close']
                buy_hold_return = ((last_price - first_price) / first_price) * 100
                buy_hold_final_capital = initial_capital * (1 + buy_hold_return / 100)

            strat_perf_list = []
            for k, v in strategy_perf.items():
                strat_perf_list.append({
                    "strategies": k,
                    "trades": v["trades"],
                    "wins": v["wins"],
                    "winRate": round(v["wins"] / v["trades"] * 100, 1) if v["trades"] > 0 else 0,
                    "pnl": round(v["pnl"], 2)
                })
            strat_perf_list.sort(key=lambda x: x["pnl"], reverse=True)

            stats = {
                "totalTrades":   total,
                "wins":          wins_count,
                "losses":        losses_count,
                "openTrades":    len(open_trades),
                "longWins":      long_wins,
                "longTotal":     long_total,
                "shortWins":     short_wins,
                "shortTotal":    short_total,
                "winRate":       round(win_rate, 1),
                "totalPnl":      round(total_pnl, 2),
                "totalProfit":   round(total_profit, 2),
                "totalLoss":     round(total_loss, 2),
                "maxDrawdown":   round(max_drawdown, 2),
                "finalCapital":  round(capital, 2),
                "initialCapital": initial_capital,
                "equityCurve":   equity_curve,
                # Advanced risk metrics
                "sortinoRatio":  round(sortino_ratio, 2),
                "calmarRatio":   round(calmar_ratio, 2),
                "maxWinStreak":  max_win_streak,
                "maxLossStreak": max_loss_streak,
                "avgWin":        round(avg_win, 2),
                "avgLoss":       round(avg_loss, 2),
                "profitFactor":  round(profit_factor, 2),
                # Buy-and-hold benchmark
                "buyHoldReturn": round(buy_hold_return, 2),
                "buyHoldFinal":  round(buy_hold_final_capital, 2),
                "vsHoldPct":     round(total_return_pct - buy_hold_return, 2),
                "strategyPerformance": strat_perf_list,
            }

            return {"candles": candles_list, "signals": signals, "stats": stats, "trades": trade_rows}

        except Exception as e:
            logger.error(f"Backtest endpoint error: {e}", exc_info=True)
            return {"error": str(e)}

    @app.post("/backtest/sweep")
    async def run_backtest_sweep(body: dict):
        """Run a small parameter sweep and rank configs by return, drawdown, and Sortino."""
        try:
            from scanner.fetcher import fetch_candles_paginated

            pair = body.get("pair", "BTCUSDT")
            interval = body.get("interval", "1m")
            limit = min(50000, max(100, int(body.get("limit", 1000))))
            top_n = min(50, max(1, int(body.get("topN", 10))))
            max_combinations = min(500, max(1, int(body.get("maxCombinations", 200))))
            sortino_weight = float(body.get("sortinoWeight", 10.0))
            drawdown_weight = float(body.get("drawdownWeight", 0.5))

            sweep = body.get("sweep", {})
            if not isinstance(sweep, dict) or not sweep:
                raise HTTPException(status_code=400, detail="sweep must be a non-empty object of parameter arrays")

            param_values = {
                key: values for key, values in sweep.items()
                if isinstance(values, list) and len(values) > 0
            }
            if not param_values:
                raise HTTPException(status_code=400, detail="sweep must contain at least one non-empty parameter list")

            keys = list(param_values.keys())
            total_configs = math.prod(len(param_values[k]) for k in keys)
            if total_configs > max_combinations:
                raise HTTPException(
                    status_code=400,
                    detail=f"sweep expands to {total_configs} configs, exceeds maxCombinations={max_combinations}",
                )
            combinations_iter = itertools.product(*(param_values[k] for k in keys))
            combinations = list(itertools.islice(combinations_iter, max_combinations))

            df = await fetch_candles_paginated(pair, interval, limit)
            if df is None or df.empty:
                return {"results": [], "evaluatedConfigs": 0, "totalConfigs": 0}

            initial_capital = float(body.get("initialCapital", 10000))
            trade_size_pct = float(body.get("tradeSizePct", 0.1))
            trade_amount = float(body.get("tradeAmount", 0))

            scored_results = []
            for values in combinations:
                combo_params = dict(zip(keys, values))
                combo_body = dict(body)
                combo_body.update(combo_params)
                custom_config = _build_backtest_config(combo_body, config)
                signals = run_backtest(df, custom_config)
                metrics = _compute_sweep_metrics(signals, initial_capital, trade_size_pct, trade_amount)
                rank_score = (
                    metrics["netReturnPct"]
                    + (metrics["sortinoRatio"] * sortino_weight)
                    - (metrics["maxDrawdown"] * drawdown_weight)
                )
                scored_results.append({
                    "params": combo_params,
                    **metrics,
                    "rankScore": round(rank_score, 4),
                })

            scored_results.sort(key=lambda x: x["rankScore"], reverse=True)
            return {
                "rankFormula": f"netReturnPct + (sortinoRatio * {sortino_weight}) - (maxDrawdown * {drawdown_weight})",
                "rankWeights": {
                    "sortinoWeight": sortino_weight,
                    "drawdownWeight": drawdown_weight,
                },
                "totalConfigs": total_configs,
                "evaluatedConfigs": len(scored_results),
                "topN": top_n,
                "results": scored_results[:top_n],
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Backtest sweep endpoint error: {e}", exc_info=True)
            return {"error": str(e)}

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        try:
            from api.websocket_server import manager
            from scanner.fetcher import CandleBuffer

            now = datetime.now(timezone.utc) if start_time.tzinfo else datetime.now()
            uptime = (now - start_time).total_seconds()

            return {
                "status": "running",
                "uptimeSeconds": int(uptime),
                "connectedClients": manager.get_connection_count(),
                "candlesBuffered": (runtime_state or {}).get("candlesBuffered", {}),
                "lastFetchLatencyMs": (runtime_state or {}).get("lastFetchLatencyMs"),
                "intervalStatus": (runtime_state or {}).get("intervalStatus", {}),
            }

        except Exception as e:
            logger.error(f"Error in health check: {e}")
            return {"status": "error", "error": str(e)}
