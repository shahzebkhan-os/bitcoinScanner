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


NATIVE_BINANCE_INTERVALS = ["1s", "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]


async def fetch_candles(pair: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
    """
    Fetch candles from Binance public API (primary) with CoinDCX fallback.
    Aggregates from 1m if interval is not natively supported.

    Args:
        pair: Trading pair (e.g., "BTCUSDT")
        interval: Time interval (e.g., "1m")
        limit: Number of candles to fetch

    Returns:
        DataFrame with columns: [time, open, high, low, close, volume]
    """
    # Check if native support exists
    if interval in NATIVE_BINANCE_INTERVALS:
        # Try Binance first (reliable, real-time data)
        df = await _fetch_candles_binance(pair, interval, limit)
        if df is not None:
            return df

        # Fallback to CoinDCX
        logger.warning(f"Binance native candle API failed for {interval}, trying CoinDCX fallback...")
        return await _fetch_candles_coindcx(pair, interval, limit)
    
    # Not natively supported, try to aggregate from 1m
    if interval.endswith('m'):
        try:
            minutes = int(interval[:-1])
            logger.info(f"Interval {interval} not native. Fetching 1m and aggregating {minutes}min.")
            
            # To get 'limit' candles of 'minutes' size, we need limit * minutes 1m candles
            # But Binance has a max limit of 1000.
            needed_1m = min(1000, limit * minutes)
            df_1m = await fetch_candles(pair, "1m", needed_1m)
            
            if df_1m is not None and not df_1m.empty:
                # Resample 1m to target interval
                # Use 'min' for minutes in pandas resample
                df_aggregated = df_1m.set_index('time').resample(f'{minutes}min').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                }).dropna().reset_index()
                
                # Take the last 'limit' candles
                return df_aggregated.tail(limit).reset_index(drop=True)
            
        except ValueError:
            logger.error(f"Invalid interval format: {interval}")
    
    return None


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


async def fetch_candles_paginated(pair: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
    """
    Fetch a large number of candles using pagination.
    Binance limits each request to 1000 candles.
    """
    if interval not in NATIVE_BINANCE_INTERVALS and not interval.endswith('m'):
         return None

    # Handle non-native m intervals by fetching 1m data and aggregating
    if interval not in NATIVE_BINANCE_INTERVALS:
        try:
            minutes = int(interval[:-1])
            # To get 'limit' candles of 'interval', we need limit * minutes of 1m candles.
            # We cap this to avoid excessive API calls (e.g., 50k * 5 = 250k candles).
            # Max 100 paginated requests (100k candles).
            fetch_limit = min(100000, limit * minutes)
            logger.info(f"Aggregating {interval} from {fetch_limit} 1m candles...")
            df_1m = await fetch_candles_paginated(pair, "1m", fetch_limit)
            
            if df_1m is not None and not df_1m.empty:
                 # Use resample to aggregate
                 df_aggregated = df_1m.set_index('time').resample(f'{minutes}min').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                 }).dropna().reset_index()
                 return df_aggregated.tail(limit).reset_index(drop=True)
            return None
        except Exception as e:
            logger.error(f"Error aggregating paginated history: {e}")
            return None

    # Native Binance pagination
    all_candles = []
    end_time = None
    chunk_size = 1000 
    remaining = limit
    
    url = "https://api.binance.com/api/v3/klines"
    
    while remaining > 0:
        current_limit = min(remaining, chunk_size)
        params = {
            "symbol": pair,
            "interval": interval,
            "limit": current_limit
        }
        if end_time:
            params["endTime"] = end_time - 1

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        logger.error(f"Binance pagination error: {response.status}")
                        break
                    data = await response.json()
                    if not data:
                        break
                    
                    # Binance returns data in ASCENDING order [oldest ... newest]
                    # Since we use endTime, we are moving backwards in time.
                    all_candles.extend(data)
                    
                    # Earliest timestamp in this batch (index 0 of the returned list)
                    first_ts = data[0][0]
                    end_time = first_ts
                    remaining -= len(data)
                    
                    if len(data) < current_limit:
                        break # No more data available
                    
                    # Respect rate limits - small delay between pages
                    await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Error in paginated fetch: {e}")
            break

    if not all_candles:
        return None

    # Process and sort all collected candles
    df = pd.DataFrame(all_candles, columns=[
        'time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base', 'taker_buy_quote', 'ignore'
    ])
    df = df[['time', 'open', 'high', 'low', 'close', 'volume']]
    df['time'] = pd.to_datetime(df['time'], unit='ms', utc=True)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Drop duplicates and sort
    df = df.drop_duplicates(subset=['time']).sort_values('time').reset_index(drop=True)
    
    logger.info(f"Fetched {len(df)} total historical candles for {pair} {interval}")
    return df


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
