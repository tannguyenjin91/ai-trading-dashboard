import asyncio
import aiohttp
from datetime import datetime

async def test():
    urls = [
        "https://services.entrade.com.vn/chart-api/v2/ohlcs/derivative?symbol=VN30F1M&resolution=1D&from=1700000000&to=2000000000",
        "https://api.dnse.com.vn/market/v1/market-status",
        "https://services.entrade.com.vn/chart-api/v2/market-status"
    ]
    async with aiohttp.ClientSession() as s:
        for u in urls:
            try:
                async with s.get(u) as r:
                    print(f"URL: {u}")
                    print(f"Status: {r.status}")
                    text = await r.read()
                    print(f"Resp length: {len(text)}")
                    if r.status == 200 and len(text) < 500:
                        print(f"Body: {text.decode('utf-8')[:500]}")
            except Exception as e:
                print(f"Error {u}: {e}")
            print("-" * 40)

asyncio.run(test())
