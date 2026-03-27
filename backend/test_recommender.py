import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ['DB_URL']='sqlite:///market_data.db'

from data.dnse_service import DnseDataIngestionService
from data.cache import aggregate_to_ohlcv
from strategy_signal.recommender import SignalRecommenderEngine
from data.store import DiskDataStore

async def test():
    store = DiskDataStore(os.environ['DB_URL'])
    dnse = DnseDataIngestionService(store)
    
    print("Fetching history...")
    bars = await dnse.fetch_history("VN30F1M", "1m", 300)
    print("Fetched", len(bars), "bars")
    
    ticks = []
    for bar in bars:
        ticks.append({
            "symbol": "VN30F1M",
            "price": float(bar.close),
            "volume": int(bar.volume),
            "timestamp": bar.timestamp.isoformat(),
            "source_timestamp": bar.timestamp.isoformat(),
            "is_mock": False
        })
        
    df_1m = aggregate_to_ohlcv(ticks, '1min')
    df_5m = aggregate_to_ohlcv(ticks, '5min')
    df_15m = aggregate_to_ohlcv(ticks, '15min')
    
    print('1m:', len(df_1m), '5m:', len(df_5m), '15m:', len(df_15m))
    
    eng = SignalRecommenderEngine()
    try:
        rec = eng.generate_recommendation(df_1m, df_5m, df_15m, 'VN30F1M')
        if rec:
            print("Recommendation:")
            print(rec.model_dump_json(indent=2))
        else:
            print("Rec returned None")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
