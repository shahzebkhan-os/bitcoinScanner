import asyncio
import aiohttp
import pandas as pd

async def test_fetch():
    url = "https://public.coindcx.com/market_data/candles"
    params = {"pair": "B-BTC_USDT", "interval": "1m", "limit": 10}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            print(f"Status: {response.status}")
            data = await response.json()
            print(f"Data length: {len(data)}")
            if data:
                print(f"First candle: {data[0]}")

if __name__ == "__main__":
    asyncio.run(test_fetch())
