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
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yaml
from typing import Optional
from scanner.backtester import run_backtest

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

            min_votes      = int(body.get("minVotes", config.get("min_votes", 3)))
            min_exit_votes = int(body.get("minExitVotes", max(1, min_votes - 1)))

            # Build custom config from body parameters
            custom_config = {
                "min_votes":       min_votes,
                "min_exit_votes":  min_exit_votes,
                # ── Strategy filters ──────────────────────────────────────────
                "useTrendFilter":  bool(body.get("useTrendFilter", False)),
                "useVolumeFilter": bool(body.get("useVolumeFilter", False)),
                "volMultiplier":   float(body.get("volMultiplier", 1.2)),
                "useHtfBias":      bool(body.get("useHtfBias", False)),
                "htfEmaPeriod":    int(body.get("htfEmaPeriod", 100)),
                "risk": {
                    "target_rr":             1.5,
                    "default_stop_loss_pct": 0.002,
                },
                "indicators": {
                    "ema_fast":       int(body.get("emaFast", 9)),
                    "ema_slow":       int(body.get("emaSlow", 21)),
                    "rsi_period":     int(body.get("rsiPeriod", 14)),
                    "rsi_oversold":   float(body.get("rsiOversold", 30)),
                    "rsi_overbought": float(body.get("rsiOverbought", 70)),
                    "macd_fast":      int(body.get("macdFast", 12)),
                    "macd_slow":      int(body.get("macdSlow", 26)),
                    "macd_signal":    int(body.get("macdSignal", 9)),
                    "bb_period":      int(body.get("bbPeriod", 20)),
                    "bb_std":         float(body.get("bbStd", 2)),
                },
            }

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

                if s.get("exitType") == "signal" and exit_p is not None:
                    pct_chg = (exit_p - entry) / entry if s["direction"] == "LONG" else (entry - exit_p) / entry
                    pnl     = trade_capital * pct_chg
                    capital += pnl
                    total_pnl += pnl
                    if pnl > 0:
                        total_profit += pnl
                        wins_count += 1
                        if s["direction"] == "LONG": long_wins += 1
                        else: short_wins += 1
                        result_label = "WIN"
                    else:
                        total_loss += pnl   # negative number
                        losses_count += 1
                        result_label = "LOSS"
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
                })

            win_rate = (wins_count / total * 100) if total > 0 else 0
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
            }

            return {"candles": candles_list, "signals": signals, "stats": stats, "trades": trade_rows}

        except Exception as e:
            logger.error(f"Backtest endpoint error: {e}", exc_info=True)
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
