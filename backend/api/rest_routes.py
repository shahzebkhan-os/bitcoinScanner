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
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yaml
from typing import Optional
import numpy as np
from scanner.backtester import run_backtest, run_custom_strategy_backtest, STRATEGY_TO_COLUMN

logger = logging.getLogger(__name__)
DEFAULT_STOP_LOSS_PCT = 0.002
CUSTOM_STRATEGY_NAMES = list(STRATEGY_TO_COLUMN.keys())
DRAWDOWN_PENALTY_MULTIPLIER = 5.0


def _snake_to_camel(key: str) -> str:
    parts = key.split("_")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def _camelize(data):
    if isinstance(data, list):
        return [_camelize(item) for item in data]
    if isinstance(data, dict):
        return {_snake_to_camel(str(k)): _camelize(v) for k, v in data.items()}
    return data


def _build_custom_config(body: dict, fallback_config: dict) -> dict:
    min_votes = int(body.get("minVotes", fallback_config.get("min_votes", 3)))
    min_exit_votes = int(body.get("minExitVotes", max(1, min_votes - 1)))
    return {
        "min_votes": min_votes,
        "min_exit_votes": min_exit_votes,
        "useTrendFilter": bool(body.get("useTrendFilter", False)),
        "useVolumeFilter": bool(body.get("useVolumeFilter", False)),
        "volMultiplier": float(body.get("volMultiplier", 1.2)),
        "useHtfBias": bool(body.get("useHtfBias", False)),
        "htfEmaPeriod": int(body.get("htfEmaPeriod", 100)),
        "risk": {
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
    }


def _compute_backtest_stats(signals: list, candles_list: list, body: dict) -> tuple[dict, list]:
    initial_capital = float(body.get("initialCapital", 10000))
    trade_size_pct = float(body.get("tradeSizePct", 0.1))
    trade_amount = float(body.get("tradeAmount", 0))

    total = len(signals)
    open_trades = [s for s in signals if s.get("exitType") == "open"]

    total_pnl = 0.0
    total_profit = 0.0
    total_loss = 0.0
    peak_capital = initial_capital
    capital = initial_capital
    max_drawdown = 0.0
    wins_count = 0
    losses_count = 0
    long_wins = 0
    long_total = 0
    short_wins = 0
    short_total = 0
    trade_rows = []
    equity_curve = [{"timestamp": signals[0]["timestamp"] if signals else "", "capital": initial_capital}]

    returns_list = []
    win_streak = 0
    loss_streak = 0
    max_win_streak = 0
    max_loss_streak = 0
    current_streak_type = None

    for s in signals:
        entry = s["entry"]
        exit_p = s.get("exitPrice")
        trade_capital = trade_amount if trade_amount > 0 else capital * trade_size_pct

        if s["direction"] == "LONG":
            long_total += 1
        else:
            short_total += 1

        if s.get("exitType") == "signal" and exit_p is not None:
            pct_chg = (exit_p - entry) / entry if s["direction"] == "LONG" else (entry - exit_p) / entry
            pnl = trade_capital * pct_chg
            capital += pnl
            total_pnl += pnl
            returns_list.append(pct_chg * 100)
            if s.get("exitTimestamp"):
                equity_curve.append({"timestamp": s["exitTimestamp"], "capital": round(capital, 2)})

            if pnl > 0:
                total_profit += pnl
                wins_count += 1
                if s["direction"] == "LONG":
                    long_wins += 1
                else:
                    short_wins += 1
                result_label = "WIN"
                if current_streak_type == "win":
                    win_streak += 1
                else:
                    win_streak = 1
                    current_streak_type = "win"
                max_win_streak = max(max_win_streak, win_streak)
                loss_streak = 0
            else:
                total_loss += pnl
                losses_count += 1
                result_label = "LOSS"
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
            "timestamp": s["timestamp"],
            "direction": s["direction"],
            "entry": round(entry, 2),
            "exit": round(exit_p or 0, 2),
            "exitType": s.get("exitType", "open"),
            "exitPrice": round(exit_p or 0, 2),
            "pnl": round(pnl, 2),
            "result": result_label,
            "votes": s["votes"],
        })

    win_rate = (wins_count / total * 100) if total > 0 else 0
    sortino_ratio = 0.0
    if len(returns_list) > 1:
        returns_arr = np.array(returns_list)
        mean_return = np.mean(returns_arr)
        downside_returns = returns_arr[returns_arr < 0]
        if len(downside_returns) > 0:
            downside_std = np.std(downside_returns)
            if downside_std > 0:
                sortino_ratio = mean_return / downside_std

    calmar_ratio = 0.0
    total_return_pct = ((capital - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0
    if max_drawdown > 0:
        calmar_ratio = total_return_pct / max_drawdown

    avg_win = (total_profit / wins_count) if wins_count > 0 else 0
    avg_loss = abs(total_loss / losses_count) if losses_count > 0 else 0
    profit_factor = (total_profit / abs(total_loss)) if total_loss != 0 else 0

    buy_hold_return = 0.0
    buy_hold_final_capital = initial_capital
    if candles_list and len(candles_list) > 1:
        first_price = candles_list[0]['close']
        last_price = candles_list[-1]['close']
        buy_hold_return = ((last_price - first_price) / first_price) * 100
        buy_hold_final_capital = initial_capital * (1 + buy_hold_return / 100)

    stats = {
        "totalTrades": total,
        "wins": wins_count,
        "losses": losses_count,
        "openTrades": len(open_trades),
        "longWins": long_wins,
        "longTotal": long_total,
        "shortWins": short_wins,
        "shortTotal": short_total,
        "winRate": round(win_rate, 1),
        "totalPnl": round(total_pnl, 2),
        "totalProfit": round(total_profit, 2),
        "totalLoss": round(total_loss, 2),
        "maxDrawdown": round(max_drawdown, 2),
        "finalCapital": round(capital, 2),
        "initialCapital": initial_capital,
        "equityCurve": equity_curve,
        "sortinoRatio": round(sortino_ratio, 2),
        "calmarRatio": round(calmar_ratio, 2),
        "maxWinStreak": max_win_streak,
        "maxLossStreak": max_loss_streak,
        "avgWin": round(avg_win, 2),
        "avgLoss": round(avg_loss, 2),
        "profitFactor": round(profit_factor, 2),
        "buyHoldReturn": round(buy_hold_return, 2),
        "buyHoldFinal": round(buy_hold_final_capital, 2),
        "vsHoldPct": round(total_return_pct - buy_hold_return, 2),
    }
    return stats, trade_rows


def _build_candles_list(df) -> list:
    return [
        {
            'time': int(row['time'].timestamp() * 1000),
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
            'volume': float(row['volume']),
        }
        for _, row in df.iterrows()
    ]


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

            pair     = body.get("pair", "BTCUSDT")
            interval = body.get("interval", "1m")
            limit    = min(50000, max(100, int(body.get("limit", 1000))))
            custom_config = _build_custom_config(body, config)

            df = await fetch_candles_paginated(pair, interval, limit)
            if df is None or df.empty:
                return {"candles": [], "signals": [], "stats": {}}

            candles_list = _build_candles_list(df)

            signals = run_backtest(df, custom_config)
            stats, trade_rows = _compute_backtest_stats(signals, candles_list, body)

            return {"candles": candles_list, "signals": signals, "stats": stats, "trades": trade_rows}

        except Exception as e:
            logger.error(f"Backtest endpoint error: {e}", exc_info=True)
            return {"error": str(e)}

    @app.post("/backtest/grid-search")
    async def run_grid_search_endpoint(body: dict):
        """Run multi-parameter grid search optimization."""
        try:
            from scanner.fetcher import fetch_candles_paginated

            pair = body.get("pair", "BTCUSDT")
            interval = body.get("interval", "1m")
            limit = min(50000, max(100, int(body.get("limit", 1000))))
            max_runs = min(200, max(1, int(body.get("maxRuns", 100))))
            top_n = min(20, max(1, int(body.get("topN", 10))))

            parameter_grid = body.get("parameterGrid", {}) or {}
            allowed_keys = {"minVotes", "minExitVotes", "rsiOversold", "rsiOverbought", "emaFast", "emaSlow"}
            grid_items = []
            for key, values in parameter_grid.items():
                if key in allowed_keys and isinstance(values, list) and values:
                    grid_items.append((key, values))

            if not grid_items:
                return {"error": "parameterGrid must include at least one valid parameter list"}

            df = await fetch_candles_paginated(pair, interval, limit)
            if df is None or df.empty:
                return {"results": [], "evaluated": 0}

            base_body = dict(body)
            combinations = itertools.product(*[vals for _, vals in grid_items])
            results = []

            for idx, combo in enumerate(combinations):
                if idx >= max_runs:
                    break
                run_body = dict(base_body)
                params_used = {}
                for i, (param_key, _) in enumerate(grid_items):
                    run_body[param_key] = combo[i]
                    params_used[param_key] = combo[i]

                custom_config = _build_custom_config(run_body, config)
                signals = run_backtest(df, custom_config)
                candles_list = _build_candles_list(df)
                stats, _ = _compute_backtest_stats(signals, candles_list, run_body)

                score = float(stats.get("finalCapital", 0.0)) - (
                    float(stats.get("maxDrawdown", 0.0)) * DRAWDOWN_PENALTY_MULTIPLIER
                )
                results.append({
                    "params": params_used,
                    "score": round(score, 2),
                    "stats": stats,
                })

            results.sort(key=lambda r: r["score"], reverse=True)
            return {
                "evaluated": len(results),
                "results": results[:top_n],
            }
        except Exception as e:
            logger.error(f"Grid search endpoint error: {e}", exc_info=True)
            return {"error": str(e)}

    @app.post("/backtest/walk-forward")
    async def run_walk_forward_endpoint(body: dict):
        """Run walk-forward optimization with in-sample/out-of-sample validation."""
        try:
            from scanner.fetcher import fetch_candles_paginated

            pair = body.get("pair", "BTCUSDT")
            interval = body.get("interval", "1m")
            limit = min(50000, max(300, int(body.get("limit", 5000))))
            train_size = min(20000, max(100, int(body.get("trainSize", 1000))))
            test_size = min(20000, max(50, int(body.get("testSize", 300))))
            step_size = min(20000, max(20, int(body.get("stepSize", test_size))))
            max_windows = min(50, max(1, int(body.get("maxWindows", 10))))

            df = await fetch_candles_paginated(pair, interval, limit)
            if df is None or df.empty:
                return {"windows": [], "summary": {}}

            windows = []
            cursor = 0
            while len(windows) < max_windows and (cursor + train_size + test_size) <= len(df):
                train_df = df.iloc[cursor:cursor + train_size].copy()
                test_df = df.iloc[cursor + train_size:cursor + train_size + test_size].copy()

                train_signals = run_backtest(train_df, _build_custom_config(body, config))
                test_signals = run_backtest(test_df, _build_custom_config(body, config))

                train_candles = _build_candles_list(train_df)
                test_candles = _build_candles_list(test_df)
                train_stats, _ = _compute_backtest_stats(train_signals, train_candles, body)
                test_stats, _ = _compute_backtest_stats(test_signals, test_candles, body)

                windows.append({
                    "windowIndex": len(windows) + 1,
                    "trainRange": {
                        "start": train_df.iloc[0]["time"].isoformat(),
                        "end": train_df.iloc[-1]["time"].isoformat(),
                    },
                    "testRange": {
                        "start": test_df.iloc[0]["time"].isoformat(),
                        "end": test_df.iloc[-1]["time"].isoformat(),
                    },
                    "inSample": train_stats,
                    "outOfSample": test_stats,
                })
                cursor += step_size

            if not windows:
                return {"windows": [], "summary": {"message": "Not enough candles for requested window sizes"}}

            avg_in = float(np.mean([w["inSample"]["finalCapital"] for w in windows]))
            avg_out = float(np.mean([w["outOfSample"]["finalCapital"] for w in windows]))
            return {
                "windows": windows,
                "summary": {
                    "windowsEvaluated": len(windows),
                    "avgInSampleFinalCapital": round(avg_in, 2),
                    "avgOutOfSampleFinalCapital": round(avg_out, 2),
                    "stabilityPct": round((avg_out / avg_in * 100), 2) if avg_in > 0 else 0.0,
                },
            }
        except Exception as e:
            logger.error(f"Walk-forward endpoint error: {e}", exc_info=True)
            return {"error": str(e)}

    @app.post("/backtest/monte-carlo")
    async def run_monte_carlo_endpoint(body: dict):
        """Run Monte Carlo simulation using trade return randomization."""
        try:
            from scanner.fetcher import fetch_candles_paginated

            pair = body.get("pair", "BTCUSDT")
            interval = body.get("interval", "1m")
            limit = min(50000, max(100, int(body.get("limit", 2000))))
            iterations = min(500, max(10, int(body.get("iterations", 200))))
            random_seed = int(body.get("seed", 42))

            df = await fetch_candles_paginated(pair, interval, limit)
            if df is None or df.empty:
                return {"simulations": [], "summary": {}}

            signals = run_backtest(df, _build_custom_config(body, config))
            closed_trades = [s for s in signals if s.get("exitType") == "signal" and s.get("exitPrice") is not None]
            if not closed_trades:
                return {"simulations": [], "summary": {"message": "No closed trades for Monte Carlo simulation"}}

            initial_capital = float(body.get("initialCapital", 10000))
            trade_amount = float(body.get("tradeAmount", 0))
            trade_size_pct = float(body.get("tradeSizePct", 0.1))

            returns = []
            for s in closed_trades:
                entry = float(s["entry"])
                exit_price = float(s["exitPrice"])
                if s["direction"] == "LONG":
                    returns.append((exit_price - entry) / entry)
                else:
                    returns.append((entry - exit_price) / entry)

            rng = np.random.default_rng(random_seed)
            final_capitals = []
            for _ in range(iterations):
                shuffled = rng.permutation(returns)
                capital = initial_capital
                for ret in shuffled:
                    trade_capital = trade_amount if trade_amount > 0 else capital * trade_size_pct
                    capital += trade_capital * float(ret)
                final_capitals.append(capital)

            arr = np.array(final_capitals)
            return {
                "summary": {
                    "iterations": iterations,
                    "meanFinalCapital": round(float(np.mean(arr)), 2),
                    "medianFinalCapital": round(float(np.median(arr)), 2),
                    "p5FinalCapital": round(float(np.percentile(arr, 5)), 2),
                    "p95FinalCapital": round(float(np.percentile(arr, 95)), 2),
                    "worstFinalCapital": round(float(np.min(arr)), 2),
                    "bestFinalCapital": round(float(np.max(arr)), 2),
                }
            }
        except Exception as e:
            logger.error(f"Monte Carlo endpoint error: {e}", exc_info=True)
            return {"error": str(e)}

    @app.post("/backtest/custom-strategy")
    async def run_custom_strategy_endpoint(body: dict):
        """Run backtest using user-selected subset of strategies."""
        try:
            from scanner.fetcher import fetch_candles_paginated

            pair = body.get("pair", "BTCUSDT")
            interval = body.get("interval", "1m")
            limit = min(50000, max(100, int(body.get("limit", 1000))))
            selected = body.get("selectedStrategies", [])
            if not isinstance(selected, list) or not selected:
                return {"error": "selectedStrategies must be a non-empty list"}
            selected = [s for s in selected if s in CUSTOM_STRATEGY_NAMES]
            if not selected:
                return {"error": "No valid strategies selected"}

            df = await fetch_candles_paginated(pair, interval, limit)
            if df is None or df.empty:
                return {"candles": [], "signals": [], "stats": {}}

            custom_config = _build_custom_config(body, config)
            min_votes = int(body.get("customMinVotes", min(2, len(selected))))
            min_exit_votes = int(body.get("customMinExitVotes", max(1, min_votes - 1)))
            signals = run_custom_strategy_backtest(
                df=df,
                config=custom_config,
                selected_strategies=selected,
                min_votes=min_votes,
                min_exit_votes=min_exit_votes,
            )

            candles_list = _build_candles_list(df)
            stats, trade_rows = _compute_backtest_stats(signals, candles_list, body)
            return {
                "candles": candles_list,
                "signals": signals,
                "stats": stats,
                "trades": trade_rows,
                "selectedStrategies": selected,
            }
        except Exception as e:
            logger.error(f"Custom strategy endpoint error: {e}", exc_info=True)
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
