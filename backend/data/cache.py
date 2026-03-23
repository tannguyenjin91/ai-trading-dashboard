# backend/data/cache.py
# Redis interoperability layer with an in-memory fallback for paper-trading without Docker.
# Handles high-frequency tick ingestion and OHLCV aggregation.

import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import pandas as pd
from loguru import logger

from data.normalizer import TickData

# In-memory fallback if Redis is unavailable
_memory_store: Dict[str, List[dict]] = {}


async def save_tick(redis_client, symbol: str, tick: TickData) -> None:
    """
    Saves a tick to the specific symbol's list.
    """
    tick_dict = tick.model_dump(mode="json")
    key = f"ticks:{symbol}"
    
    if redis_client:
        try:
            # Push to right of list
            await redis_client.rpush(key, json.dumps(tick_dict))
            # Keep only last 10000 ticks to prevent memory bloat
            await redis_client.ltrim(key, -10000, -1)
            return
        except Exception as e:
            logger.error(f"Redis save failed: {e}")
            
    # Fallback to in-memory
    if key not in _memory_store:
        _memory_store[key] = []
    _memory_store[key].append(tick_dict)
    if len(_memory_store[key]) > 10000:
        _memory_store[key] = _memory_store[key][-10000:]


async def get_recent_ticks(redis_client, symbol: str, limit: int = 5000) -> List[dict]:
    """
    Retrieves the most recent ticks for a symbol.
    """
    key = f"ticks:{symbol}"
    
    if redis_client:
        try:
            raw_ticks = await redis_client.lrange(key, -limit, -1)
            return [json.loads(r) for r in raw_ticks]
        except Exception as e:
            logger.error(f"Redis fetch failed: {e}")
            
    # Fallback
    return _memory_store.get(key, [])[-limit:]


def aggregate_to_ohlcv(ticks: List[dict], timeframe: str = "1min") -> pd.DataFrame:
    """
    Groups purely tick-level dictionaries into an OHLCV Pandas DataFrame.
    """
    if not ticks:
        return pd.DataFrame()
        
    df = pd.DataFrame(ticks)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)
    
    # Resample
    ohlcv = df["price"].resample(timeframe).ohlc()
    ohlcv["volume"] = df["volume"].resample(timeframe).sum()
    
    # Forward fill missing closes, then backfill remaining, and fill N/A volumes with 0
    ohlcv["close"] = ohlcv["close"].ffill().bfill()
    ohlcv["open"] = ohlcv["open"].fillna(ohlcv["close"])
    ohlcv["high"] = ohlcv["high"].fillna(ohlcv["close"])
    ohlcv["low"] = ohlcv["low"].fillna(ohlcv["close"])
    ohlcv["volume"] = ohlcv["volume"].fillna(0)
    
    return ohlcv.dropna()
