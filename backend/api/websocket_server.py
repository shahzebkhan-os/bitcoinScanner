"""
WebSocket Server Module - api/websocket_server.py

Responsibilities:
- Manage WebSocket connections
- Broadcast tick data to all connected clients
- Handle connection/disconnection gracefully
"""

import logging
import json
from typing import List
from fastapi import WebSocket, WebSocketDisconnect

from scanner.indicators import IndicatorSnapshot
from scanner.strategies import SignalResult
from scanner.consensus import ConsensusResult

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept and register new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """
        Broadcast message to all connected clients.

        Args:
            message: Dictionary to send as JSON
        """
        if not self.active_connections:
            return

        disconnected = []
        message_str = json.dumps(message)

        for connection in self.active_connections:
            try:
                await connection.send_text(message_str)
            except Exception as e:
                logger.error(f"Error sending to client: {e}")
                disconnected.append(connection)

        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

    def get_connection_count(self) -> int:
        """Return number of active connections."""
        return len(self.active_connections)


# Global connection manager
manager = ConnectionManager()


async def broadcast_tick(
    candles: list[dict],
    snapshot: IndicatorSnapshot,
    results: list[SignalResult],
    consensus: ConsensusResult
):
    """
    Broadcast tick data to all connected clients.

    Args:
        candles: Last 100 candles as dictionaries
        snapshot: Current indicator snapshot
        results: List of strategy results
        consensus: Consensus result
    """
    try:
        payload = {
            "type": "tick",
            "timestamp": snapshot.timestamp.isoformat(),
            "price": snapshot.current_price,
            "candles": candles,
            "indicators": snapshot.to_dict(),
            "strategies": [
                {
                    "strategyName": r.strategy_name,
                    "direction": r.direction,
                    "strength": r.strength,
                    "reason": r.reason
                }
                for r in results
            ],
            "consensus": consensus.to_dict(),
            "signalFired": consensus.fired
        }

        await manager.broadcast(payload)

    except Exception as e:
        logger.error(f"Error broadcasting tick: {e}")


async def broadcast_signal(consensus: ConsensusResult, snapshot: IndicatorSnapshot):
    """
    Broadcast signal message when consensus fires.

    Args:
        consensus: Consensus result
        snapshot: Indicator snapshot
    """
    try:
        payload = {
            "type": "signal",
            "timestamp": snapshot.timestamp.isoformat(),
            "direction": consensus.direction,
            "price": snapshot.current_price,
            "votes": f"{len(consensus.agreeing_strategies)}/6",
            "strategies": consensus.agreeing_strategies,
            "strength": consensus.avg_strength,
            "rsi": snapshot.rsi,
            "volumeRatio": snapshot.volume_ratio
        }

        await manager.broadcast(payload)

    except Exception as e:
        logger.error(f"Error broadcasting signal: {e}")
