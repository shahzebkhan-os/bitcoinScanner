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
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yaml

logger = logging.getLogger(__name__)


def setup_routes(app: FastAPI, config: dict, start_time: datetime):
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

            return sanitized
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

            return {"signals": signals}

        except Exception as e:
            logger.error(f"Error reading signals history: {e}")
            return {"error": str(e)}

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        try:
            from api.websocket_server import manager
            from scanner.fetcher import CandleBuffer

            uptime = (datetime.now() - start_time).total_seconds()

            return {
                "status": "running",
                "uptime_seconds": int(uptime),
                "connected_clients": manager.get_connection_count()
            }

        except Exception as e:
            logger.error(f"Error in health check: {e}")
            return {"status": "error", "error": str(e)}
