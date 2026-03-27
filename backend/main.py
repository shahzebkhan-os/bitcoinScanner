"""
Main Application Module - main.py

Entry point for the Bitcoin Scanner.
Runs FastAPI server and scanner loop concurrently.
"""

import asyncio
import logging
import time
from datetime import datetime
import yaml
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

# Scanner modules
from scanner.fetcher import fetch_candles, CandleBuffer
from scanner.indicators import calculate_indicators
from scanner.strategies import run_all_strategies
from scanner.consensus import evaluate_consensus
from scanner.alerts import dispatch_alerts

# API modules
from api.websocket_server import manager, broadcast_tick, broadcast_signal
from api.rest_routes import setup_routes

# Logger
from logger.signal_log import log_signal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load configuration
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# FastAPI app
app = FastAPI(title="Bitcoin Scanner API")

# Start time for uptime tracking
start_time = datetime.now()

# Set up REST routes
setup_routes(app, config, start_time)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time data streaming."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive - client sends pings
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# Signal cooldown tracking
last_signal_time = {}
COOLDOWN_SECONDS = 60


async def scanner_loop():
    """Main scanner loop - polls API every second and evaluates strategies."""
    logger.info("Starting scanner loop...")

    buffer = CandleBuffer(config['candle_buffer_size'])

    while True:
        start = time.monotonic()

        try:
            # Fetch candles
            candles = await fetch_candles(
                pair=config['pair'],
                interval=config['interval'],
                limit=config['candle_buffer_size']
            )

            if candles is not None and not candles.empty:
                # Update buffer
                updated = buffer.update(candles)

                if len(buffer) >= 50:
                    # Get current buffer
                    df = buffer.get()

                    # Calculate indicators
                    snapshot = calculate_indicators(df, config)

                    if snapshot is not None:
                        # Run strategies
                        results = run_all_strategies(snapshot, config, df)

                        # Evaluate consensus
                        consensus = evaluate_consensus(results, config)

                        # Always broadcast tick (Angular dashboard needs it)
                        await broadcast_tick(
                            candles=buffer.get_last_n_as_dicts(100),
                            snapshot=snapshot,
                            results=results,
                            consensus=consensus
                        )

                        # Check if consensus fired
                        if consensus.fired:
                            # Check cooldown
                            current_time = time.time()
                            last_time = last_signal_time.get(consensus.direction, 0)

                            if current_time - last_time >= COOLDOWN_SECONDS:
                                # Dispatch alerts
                                dispatch_alerts(consensus, snapshot, config)

                                # Log signal
                                log_signal(consensus, snapshot)

                                # Broadcast signal message
                                await broadcast_signal(consensus, snapshot)

                                # Update cooldown
                                last_signal_time[consensus.direction] = current_time
                            else:
                                logger.info(f"Signal suppressed - cooldown active for {consensus.direction}")

        except Exception as e:
            logger.error(f"Error in scanner loop: {e}", exc_info=True)

        # Sleep to maintain polling interval
        elapsed = time.monotonic() - start
        sleep_time = max(0, config['poll_interval_seconds'] - elapsed)
        await asyncio.sleep(sleep_time)


async def startup():
    """Start FastAPI server and scanner loop concurrently."""
    logger.info("Starting Bitcoin Scanner...")
    logger.info(f"Config: {config['pair']} @ {config['interval']}")
    logger.info(f"WebSocket: ws://{config['websocket']['host']}:{config['websocket']['port']}/ws")

    # Create uvicorn server
    server_config = uvicorn.Config(
        app,
        host=config['websocket']['host'],
        port=config['websocket']['port'],
        log_level="warning",
        loop="asyncio"
    )
    server = uvicorn.Server(server_config)

    # Run server and scanner concurrently
    await asyncio.gather(
        server.serve(),
        scanner_loop()
    )


if __name__ == "__main__":
    try:
        asyncio.run(startup())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
