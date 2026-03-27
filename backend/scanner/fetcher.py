"""
Data Fetching Module - scanner/fetcher.py

Responsibilities:
- Fetch candles from CoinDCX public API
- Parse JSON response into pandas DataFrame
- Maintain a rolling buffer of candles
- Handle HTTP errors with exponential backoff retry
"""

import asyncio
import logging
from collections import deque
from typing import Optional
import aiohttp
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)


async def fetch_candles(pair: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
    """
    Fetch candles from CoinDCX public API with retry logic.

    Args:
        pair: Trading pair (e.g., "B-BTC_USDT")
        interval: Time interval (e.g., "1m")
        limit: Number of candles to fetch

    Returns:
        DataFrame with columns: [time, open, high, low, close, volume]
    """
    url = "https://public.coindcx.com/market_data/candles"
    params = {"pair": pair, "interval": interval, "limit": limit}

    max_retries = 3
    retry_delays = [1, 2, 4]  # Exponential backoff in seconds

    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 429:
                        logger.warning("Rate limited (429), backing off 5 seconds")
                        await asyncio.sleep(5)
                        continue

                    response.raise_for_status()
                    data = await response.json()

                    if not data:
                        logger.warning("Empty response from API")
                        return None

                    # Parse into DataFrame
                    df = pd.DataFrame(data)

                    # Validate required columns
                    required_cols = ['time', 'open', 'high', 'low', 'close', 'volume']
                    if not all(col in df.columns for col in required_cols):
                        logger.error(f"Missing required columns in response: {df.columns}")
                        return None

                    # Convert time from milliseconds to datetime
                    df['time'] = pd.to_datetime(df['time'], unit='ms', utc=True)

                    # Ensure numeric types
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')

                    # Drop rows with NaN values
                    df = df.dropna()

                    # Sort by time ascending
                    df = df.sort_values('time').reset_index(drop=True)

                    logger.debug(f"Fetched {len(df)} candles")
                    return df

        except aiohttp.ClientError as e:
            logger.error(f"HTTP error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delays[attempt])
            else:
                logger.error("Max retries exceeded")
                return None
        except Exception as e:
            logger.error(f"Unexpected error fetching candles: {e}")
            return None

    return None


class CandleBuffer:
    """
    Maintains a rolling buffer of candle data.
    """

    def __init__(self, buffer_size: int = 200):
        """
        Initialize the candle buffer.

        Args:
            buffer_size: Maximum number of candles to store
        """
        self.buffer_size = buffer_size
        self.candles: deque = deque(maxlen=buffer_size)
        self.last_timestamp: Optional[datetime] = None

    def update(self, new_candles: pd.DataFrame) -> bool:
        """
        Update buffer with new candles, avoiding duplicates.

        Args:
            new_candles: DataFrame with new candle data

        Returns:
            True if new candle was added, False otherwise
        """
        if new_candles is None or new_candles.empty:
            return False

        # Get the latest candle from new data
        latest_candle = new_candles.iloc[-1]
        latest_timestamp = latest_candle['time']

        # Check if this is a genuinely new candle
        if self.last_timestamp is not None and latest_timestamp <= self.last_timestamp:
            return False

        # Add new candle to buffer
        self.candles.append(latest_candle.to_dict())
        self.last_timestamp = latest_timestamp

        logger.debug(f"Buffer updated: {len(self.candles)} candles, latest: {latest_timestamp}")
        return True

    def get(self) -> pd.DataFrame:
        """
        Get current buffer as DataFrame.

        Returns:
            DataFrame with all buffered candles
        """
        if not self.candles:
            return pd.DataFrame()

        df = pd.DataFrame(list(self.candles))
        return df

    def get_last_n_as_dicts(self, n: int) -> list[dict]:
        """
        Get last N candles as list of dictionaries for WebSocket broadcast.

        Args:
            n: Number of candles to return

        Returns:
            List of candle dictionaries
        """
        if not self.candles:
            return []

        last_n = list(self.candles)[-n:]
        result = []

        for candle in last_n:
            result.append({
                'time': int(candle['time'].timestamp() * 1000),  # Convert to milliseconds
                'open': float(candle['open']),
                'high': float(candle['high']),
                'low': float(candle['low']),
                'close': float(candle['close']),
                'volume': float(candle['volume'])
            })

        return result

    def __len__(self) -> int:
        """Return current buffer size."""
        return len(self.candles)
