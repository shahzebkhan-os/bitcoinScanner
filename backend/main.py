"""
Main Application Module - main.py

Entry point for the Bitcoin Scanner.
Runs FastAPI server and scanner loop concurrently.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any
import yaml
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

# Scanner modules
from scanner.fetcher import fetch_candles, fetch_ticker, CandleBuffer
from scanner.indicators import calculate_indicators
from scanner.strategies import run_all_strategies
from scanner.consensus import evaluate_consensus, ConsensusResult
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


def _build_overall_trend(
    interval_results: dict[str, dict],
    interval_consensus: dict[str, Any],
) -> dict:
    """
    Build an overall trend summary for the next 1 minute based on 1m/2m/3m votes.
    """
    long_votes = 0
    short_votes = 0
    neutral_votes = 0

    per_interval = {}
    for interval, results in interval_results.items():
        long_count = sum(1 for r in results["strategies"] if r.direction == "LONG")
        short_count = sum(1 for r in results["strategies"] if r.direction == "SHORT")
        neutral_count = sum(1 for r in results["strategies"] if r.direction == "NEUTRAL")
        long_votes += long_count
        short_votes += short_count
        neutral_votes += neutral_count
        per_interval[interval] = {
            "longVotes": long_count,
            "shortVotes": short_count,
            "neutralVotes": neutral_count,
            "consensus": interval_consensus[interval].direction,
        }

    if long_votes > short_votes:
        direction = "BULLISH"
    elif short_votes > long_votes:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    total_votes = max(1, long_votes + short_votes + neutral_votes)
    confidence = round(max(long_votes, short_votes) / total_votes, 4)

    return {
        "timeHorizon": "next_1m",
        "direction": direction,
        "confidence": confidence,
        "totalLongVotes": long_votes,
        "totalShortVotes": short_votes,
        "totalNeutralVotes": neutral_votes,
        "intervals": per_interval,
    }


async def scanner_loop():
    """Main scanner loop - polls API every second and evaluates strategies."""
    logger.info("Starting scanner loop...")

    scan_intervals = config.get('scan_intervals', ['1m'])
    if not scan_intervals:
        scan_intervals = ['1m']
    chart_interval = config.get('interval', '1m')
    if chart_interval not in scan_intervals:
        chart_interval = scan_intervals[0]
    chart_history_candles = config.get('chart_history_candles', 100)

    buffers = {
        interval: CandleBuffer(config['candle_buffer_size'])
        for interval in scan_intervals
    }

    while True:
        start = time.monotonic()

        try:
            # Fetch ticker for real-time price update
            ticker_price = await fetch_ticker(config['pair'])

            interval_results = {}
            interval_consensus = {}
            chart_snapshot = None
            chart_results = []
            chart_consensus = None

            for interval in scan_intervals:
                candles = await fetch_candles(
                    pair=config['pair'],
                    interval=interval,
                    limit=config['candle_buffer_size']
                )
                if candles is None or candles.empty:
                    continue

                buffer = buffers[interval]
                buffer.update(candles)

                if len(buffer) < 50:
                    continue

                df = buffer.get()
                snapshot = calculate_indicators(df, config)
                if snapshot is None:
                    continue

                results = run_all_strategies(snapshot, config, df)
                consensus = evaluate_consensus(results, config)

                interval_results[interval] = {
                    "snapshot": snapshot,
                    "strategies": results,
                }
                interval_consensus[interval] = consensus

                if interval == chart_interval:
                    chart_snapshot = snapshot
                    chart_results = results
                    chart_consensus = consensus

            if not interval_results:
                continue

            # Update latest candle in configured chart interval with real-time ticker
            if ticker_price and chart_interval in buffers:
                buffers[chart_interval].update_latest_price(ticker_price)
                if chart_snapshot:
                    chart_snapshot.current_price = ticker_price

            # Fallback chart interval if configured one unavailable
            if chart_snapshot is None or chart_consensus is None:
                fallback_interval = next(i for i in scan_intervals if i in interval_results)
                chart_interval = fallback_interval
                chart_snapshot = interval_results[fallback_interval]["snapshot"]
                chart_results = interval_results[fallback_interval]["strategies"]
                chart_consensus = interval_consensus[fallback_interval]

            overall_trend = _build_overall_trend(interval_results, interval_consensus)

            # Use aggregated majority vote for actionable signal
            total_long = overall_trend["totalLongVotes"]
            total_short = overall_trend["totalShortVotes"]
            aggregated_direction = "LONG" if total_long > total_short else "SHORT" if total_short > total_long else "NEUTRAL"

            if aggregated_direction != "NEUTRAL":
                agreeing = []
                strength_total = 0.0
                for interval, data in interval_results.items():
                    for strategy in data["strategies"]:
                        if strategy.direction == aggregated_direction:
                            agreeing.append(f"{interval}:{strategy.strategy_name}")
                            strength_total += strategy.strength

                if agreeing:
                    chart_consensus = ConsensusResult(
                        direction=aggregated_direction,
                        long_votes=total_long,
                        short_votes=total_short,
                        neutral_votes=overall_trend["totalNeutralVotes"],
                        avg_strength=strength_total / len(agreeing),
                        agreeing_strategies=agreeing,
                        fired=len(agreeing) >= config.get('min_votes', 3),
                    )

            # Always broadcast tick
            await broadcast_tick(
                candles=buffers[chart_interval].get_last_n_as_dicts(chart_history_candles),
                snapshot=chart_snapshot,
                results=chart_results,
                consensus=chart_consensus,
                overall_trend=overall_trend,
            )

            # Check if consensus fired
            if chart_consensus.fired:
                current_time = time.time()
                last_time = last_signal_time.get(chart_consensus.direction, 0)

                if current_time - last_time >= COOLDOWN_SECONDS:
                    dispatch_alerts(chart_consensus, chart_snapshot, config)
                    log_signal(chart_consensus, chart_snapshot)
                    await broadcast_signal(chart_consensus, chart_snapshot)
                    last_signal_time[chart_consensus.direction] = current_time
                else:
                    logger.info(f"Signal suppressed - cooldown active for {chart_consensus.direction}")

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
