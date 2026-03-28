"""
Data Fetching Module - scanner/fetcher.py

Responsibilities:
- Fetch candles from Binance public API (primary) with CoinDCX fallback
- Fetch real-time ticker price from Binance (primary) with CoinDCX fallback
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
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def fetch_candles(pair: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
    """
    Fetch candles from Binance public API (primary) with CoinDCX fallback.

    Args:
        pair: Trading pair (e.g., "BTCUSDT")
        interval: Time interval (e.g., "1m")
        limit: Number of candles to fetch

    Returns:
        DataFrame with columns: [time, open, high, low, close, volume]
    """
    # Try Binance first (reliable, real-time data)
    df = await _fetch_candles_binance(pair, interval, limit)
    if df is not None:
        return df

    # Fallback to CoinDCX
    logger.warning("Binance candle API failed, trying CoinDCX fallback...")
    return await _fetch_candles_coindcx(pair, interval, limit)


async def _fetch_candles_binance(pair: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
    """Fetch candles from Binance /api/v3/klines."""
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": pair, "interval": interval, "limit": limit}

    max_retries = 3
    retry_delays = [1, 2, 4]

    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 429:
                        logger.warning("Binance rate limited (429), backing off 5s")
                        await asyncio.sleep(5)
                        continue

                    if response.status == 451:
                        logger.warning("Binance returned 451 (geo-restricted), skipping")
                        return None

                    response.raise_for_status()
                    data = await response.json()

                    if not data:
                        logger.warning("Empty response from Binance klines API")
                        return None

                    # Binance klines format: [[open_time, open, high, low, close, volume, close_time, ...], ...]
                    df = pd.DataFrame(data, columns=[
                        'time', 'open', 'high', 'low', 'close', 'volume',
                        'close_time', 'quote_asset_volume', 'number_of_trades',
                        'taker_buy_base', 'taker_buy_quote', 'ignore'
                    ])

                    # Keep only OHLCV columns
                    df = df[['time', 'open', 'high', 'low', 'close', 'volume']]

                    # Convert time from milliseconds to datetime
                    df['time'] = pd.to_datetime(df['time'], unit='ms', utc=True)

                    # Ensure numeric types
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')

                    # Drop rows with NaN values
                    df = df.dropna()

                    # Sort by time ascending
                    df = df.sort_values('time').reset_index(drop=True)

                    logger.info(f"Fetched {len(df)} candles from Binance for {pair} (latest: {df.iloc[-1]['close']:.2f})")
                    return df

        except aiohttp.ClientError as e:
            logger.error(f"Binance HTTP error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delays[attempt])
        except Exception as e:
            logger.error(f"Unexpected error fetching from Binance: {e}")
            break

    return None


async def _fetch_candles_coindcx(pair: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
    """Fetch candles from CoinDCX (fallback)."""
    pairs_to_try = [pair]
    if "BTC" in pair:
        if "B-BTC_USDT" not in pairs_to_try:
            pairs_to_try.append("B-BTC_USDT")
    elif "ETH" in pair:
        if "B-ETH_USDT" not in pairs_to_try:
            pairs_to_try.append("B-ETH_USDT")

    for current_pair in pairs_to_try:
        url = "https://public.coindcx.com/market_data/candles"
        params = {"pair": current_pair, "interval": interval, "limit": limit}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    response.raise_for_status()
                    data = await response.json()

                    if not data:
                        logger.debug(f"Empty CoinDCX response for {current_pair}")
                        continue

                    df = pd.DataFrame(data)
                    required_cols = ['time', 'open', 'high', 'low', 'close', 'volume']
                    if not all(col in df.columns for col in required_cols):
                        continue

                    df['time'] = pd.to_datetime(df['time'], unit='ms', utc=True)
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    df = df.dropna().sort_values('time').reset_index(drop=True)

                    logger.info(f"Fetched {len(df)} candles from CoinDCX fallback for {current_pair}")
                    return df

        except Exception as e:
            logger.error(f"CoinDCX fallback error for {current_pair}: {e}")

    return None


async def fetch_ticker(pair: str) -> Optional[float]:
    """
    Fetch the latest price from Binance (primary) with CoinDCX fallback.

    Args:
        pair: Trading pair (e.g., "BTCUSDT")

    Returns:
        Latest price as a float, or None if fetch fails
    """
    # Try Binance first
    price = await _fetch_ticker_binance(pair)
    if price is not None:
        return price

    # Fallback to CoinDCX
    return await _fetch_ticker_coindcx(pair)


async def _fetch_ticker_binance(pair: str) -> Optional[float]:
    """Fetch price from Binance /api/v3/ticker/price."""
    url = "https://api.binance.com/api/v3/ticker/price"
    params = {"symbol": pair}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 451:
                    return None
                response.raise_for_status()
                data = await response.json()
                return float(data.get('price', 0))
    except Exception as e:
        logger.debug(f"Binance ticker error: {e}")
        return None


async def _fetch_ticker_coindcx(pair: str) -> Optional[float]:
    """Fetch price from CoinDCX (fallback)."""
    url = "https://api.coindcx.com/exchange/ticker"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                response.raise_for_status()
                data = await response.json()

                for item in data:
                    if item.get('market') == pair:
                        return float(item.get('last_price'))

                for item in data:
                    if item.get('market') == f"B-{pair}":
                        return float(item.get('last_price'))

                return None
    except Exception as e:
        logger.error(f"CoinDCX ticker error: {e}")
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

        if not self.candles:
            # Initial load - ingest all candles from the dataframe
            for _, row in new_candles.iterrows():
                self.candles.append(row.to_dict())
            self.last_timestamp = new_candles.iloc[-1]['time']
            logger.info(f"Initial buffer load: {len(self.candles)} candles, latest: {self.last_timestamp}")
            return True

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

    def update_latest_price(self, price: float):
        """
        Update the close price of the most recent candle in the buffer.
        Also updates high/low if the new price exceeds them.
        """
        if not self.candles:
            return
            
        latest = self.candles[-1]
        latest['close'] = price
        if price > latest['high']:
            latest['high'] = price
        if price < latest['low']:
            latest['low'] = price

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
