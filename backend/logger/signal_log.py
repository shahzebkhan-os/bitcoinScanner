"""
Signal Logger Module - logger/signal_log.py

Responsibilities:
- Write fired signals to CSV file
- Include full indicator snapshot
- Append to existing file
"""

import logging
import csv
import os
from datetime import datetime
from typing import Optional
from pathlib import Path

from scanner.indicators import IndicatorSnapshot
from scanner.consensus import ConsensusResult

logger = logging.getLogger(__name__)

CSV_FILE = "signals_log.csv"
CSV_HEADERS = [
    'timestamp', 'direction', 'price', 'votes', 'strategies',
    'avg_strength', 'rsi', 'macd_histogram', 'volume_ratio',
    'ema_fast', 'ema_slow', 'bb_upper', 'bb_lower', 'vwap',
    'interval', 'entry', 'stop_loss', 'target', 'target_rr',
    'entry_timestamp', 'entry_direction'
]


def log_signal(consensus: ConsensusResult, snapshot: IndicatorSnapshot, trade_levels: Optional[dict] = None):
    """
    Log signal to CSV file.

    Args:
        consensus: Consensus result
        snapshot: Indicator snapshot
    """
    try:
        levels = trade_levels or {}
        # Check if file exists
        file_exists = os.path.isfile(CSV_FILE)

        with open(CSV_FILE, 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=CSV_HEADERS)

            # Write header if new file
            if not file_exists:
                writer.writeheader()

            # Write signal row
            writer.writerow({
                'timestamp': snapshot.timestamp.isoformat(),
                'direction': consensus.direction,
                'price': f"{snapshot.current_price:.2f}",
                'votes': f"{len(consensus.agreeing_strategies)}/6",
                'strategies': '; '.join(consensus.agreeing_strategies),
                'avg_strength': f"{consensus.avg_strength:.2f}",
                'rsi': f"{snapshot.rsi:.1f}",
                'macd_histogram': f"{snapshot.macd_histogram:.2f}",
                'volume_ratio': f"{snapshot.volume_ratio:.2f}",
                'ema_fast': f"{snapshot.ema_fast:.2f}",
                'ema_slow': f"{snapshot.ema_slow:.2f}",
                'bb_upper': f"{snapshot.bb_upper:.2f}",
                'bb_lower': f"{snapshot.bb_lower:.2f}",
                'vwap': f"{snapshot.vwap:.2f}",
                'interval': levels.get('interval', ''),
                'entry': f"{levels.get('entry', snapshot.current_price):.2f}" if levels.get('entry', snapshot.current_price) is not None else "",
                'stop_loss': f"{levels.get('stopLoss', None):.2f}" if levels.get('stopLoss', None) is not None else "",
                'target': f"{levels.get('target', None):.2f}" if levels.get('target', None) is not None else "",
                'target_rr': f"{levels.get('targetRr', None):.2f}" if levels.get('targetRr', None) is not None else "",
                'entry_timestamp': levels.get('timestamp', snapshot.timestamp.isoformat()),
                'entry_direction': levels.get('direction', consensus.direction),
            })

        logger.info(f"Signal logged to {CSV_FILE}")

    except Exception as e:
        logger.error(f"Error logging signal to CSV: {e}")
