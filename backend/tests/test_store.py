# backend/tests/test_store.py
import pytest
import os
from datetime import datetime, timezone
from data.store import DiskDataStore

@pytest.mark.asyncio
async def test_store_persistence():
    db_path = "test_market_data.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    store = DiskDataStore(db_path=db_path)
    await store.init_db()
    
    symbol = "TEST_SYM"
    ts = datetime.now(timezone.utc)
    ohlcv = {"open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0, "volume": 1000.0}
    
    await store.save_candle(symbol, ts, ohlcv, timeframe="1m")
    
    df = await store.get_recent_candles(symbol, limit=10, timeframe="1m")
    
    assert not df.empty
    assert len(df) == 1
    assert df.iloc[0]["close"] == 105.0
    
    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)
