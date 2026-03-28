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


def setup_routes(app: FastAPI, config: dict, start_time: datetime, runtime_state: dict | None = None):
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
    async def get_signals_history(limit: int = 50):
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
