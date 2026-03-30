"""
Alerts Module - scanner/alerts.py

Responsibilities:
- Dispatch alerts to terminal (color-coded)
- Send desktop notifications
- Send Telegram messages (optional)
"""

import logging
from datetime import datetime
from typing import Optional

from colorama import Fore, Style, init
from plyer import notification

from scanner.indicators import IndicatorSnapshot
from scanner.consensus import ConsensusResult

# Initialize colorama
init(autoreset=True)

logger = logging.getLogger(__name__)


def _vote_capacity(consensus: ConsensusResult) -> int:
    return max(1, consensus.long_votes + consensus.short_votes + consensus.neutral_votes)


def dispatch_alerts(consensus: ConsensusResult, snapshot: IndicatorSnapshot, config: dict):
    """
    Dispatch alerts based on configuration.

    Args:
        consensus: Consensus result with direction and votes
        snapshot: Current indicator snapshot
        config: Configuration dict with alert settings
    """
    alert_config = config.get('alerts', {})

    # Terminal alert
    if alert_config.get('terminal', True):
        _send_terminal_alert(consensus, snapshot)

    # Desktop notification
    if alert_config.get('desktop', True):
        _send_desktop_alert(consensus, snapshot)

    # Telegram alert
    if alert_config.get('telegram', False):
        _send_telegram_alert(consensus, snapshot, config)


def _send_terminal_alert(consensus: ConsensusResult, snapshot: IndicatorSnapshot):
    """Send color-coded alert to terminal."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if consensus.direction == "LONG":
            color = Fore.GREEN
            symbol = "▲"
        elif consensus.direction == "SHORT":
            color = Fore.RED
            symbol = "▼"
        else:
            color = Fore.YELLOW
            symbol = "●"

        # Format message
        vote_capacity = _vote_capacity(consensus)
        message = f"""
{color}{'=' * 80}{Style.RESET_ALL}
{color}{symbol} SIGNAL FIRED: {consensus.direction} {symbol}{Style.RESET_ALL}
{color}{'=' * 80}{Style.RESET_ALL}
Timestamp: {timestamp}
Price: ${snapshot.current_price:,.2f}
Votes: {len(consensus.agreeing_strategies)}/{vote_capacity}
Strength: {consensus.avg_strength:.2f}
Strategies: {', '.join(consensus.agreeing_strategies)}

Indicators:
  RSI: {snapshot.rsi:.1f}
  MACD Histogram: {snapshot.macd_histogram:.2f}
  Volume Ratio: {snapshot.volume_ratio:.2f}x
{color}{'=' * 80}{Style.RESET_ALL}
"""
        print(message)

    except Exception as e:
        logger.error(f"Error sending terminal alert: {e}")


def _send_desktop_alert(consensus: ConsensusResult, snapshot: IndicatorSnapshot):
    """Send desktop notification."""
    try:
        title = f"🔔 {consensus.direction} Signal"
        vote_capacity = _vote_capacity(consensus)
        message = (
            f"Price: ${snapshot.current_price:,.2f}\n"
            f"Votes: {len(consensus.agreeing_strategies)}/{vote_capacity}\n"
            f"Strength: {consensus.avg_strength:.2f}"
        )

        notification.notify(
            title=title,
            message=message,
            app_name="Bitcoin Scanner",
            timeout=10
        )

    except Exception as e:
        logger.error(f"Error sending desktop notification: {e}")


def _send_telegram_alert(consensus: ConsensusResult, snapshot: IndicatorSnapshot, config: dict):
    """Send Telegram message (optional)."""
    try:
        telegram_config = config.get('telegram', {})
        bot_token = telegram_config.get('bot_token', '')
        chat_id = telegram_config.get('chat_id', '')

        if not bot_token or not chat_id:
            logger.warning("Telegram not configured, skipping")
            return

        # Note: Actual implementation would use python-telegram-bot library
        # For now, just log that we would send
        logger.info(f"Would send Telegram alert: {consensus.direction} at ${snapshot.current_price:,.2f}")

    except Exception as e:
        logger.error(f"Error sending Telegram alert: {e}")
