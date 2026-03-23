import aiohttp
import asyncio
import time

async def test():
    async with aiohttp.ClientSession() as s:
        now = int(time.time())
        from_ts = now - 30 * 86400

        for endpoint, sym in [('stock', 'SSI'), ('derivative', 'VN30F1M'), ('derivative', 'VN30F2406'), ('index', 'VN30')]:
            for res in ['1', '1D', 'D']:
                url = f'https://services.entrade.com.vn/chart-api/v2/ohlcs/{endpoint}'
                params = {'from': from_ts, 'to': now, 'symbol': sym, 'resolution': res}
                r = await s.get(url, params=params)
                if r.status == 200:
                    data = await r.json()
                    t = data.get('t')
                    if t is None:
                        t = []
                    print(f"{endpoint} {sym} res={res} -> {len(t)} candles")
                else:
                    print(f"{endpoint} {sym} res={res} -> HTTP {r.status}")

if __name__ == "__main__":
    asyncio.run(test())
