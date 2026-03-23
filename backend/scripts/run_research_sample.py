# backend/scripts/run_research_sample.py
import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from data.store import DiskDataStore
from data.dnse_service import DnseDataIngestionService
from data.feature_store import FeatureStoreService
from strategy_signal.research_engine import ResearchEngineService

async def main():
    print("Starting Sample Research Task...")
    
    # 1. Setup Infrastructure
    store = DiskDataStore(db_path="market_data.db")
    await store.init_db()
    
    feature_store = FeatureStoreService(store=store)
    dnse = DnseDataIngestionService(store=store)
    research_engine = ResearchEngineService(store=store, feature_store=feature_store)
    
    symbol = "VN30F2406"
    
    # 2. Backfill from DNSE (Pipeline 1)
    # Using mock data by default in service for now
    await dnse.backfill_symbol(symbol, timeframe="1D")
    
    # 3. Running factors on historical data
    features = await feature_store.calculate_features(symbol, timeframe="1D")
    if features:
        print(f"Features calculated for {symbol}: {features.features}")
    
    # 4. Running an offline backtest
    results = await research_engine.run_offline_backtest(symbol, strategy_func=None)
    print(f"Backtest Results: {results}")

if __name__ == "__main__":
    asyncio.run(main())
