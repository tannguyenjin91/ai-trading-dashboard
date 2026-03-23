# backend/data/dnse_service.py
import asyncio
import aiohttp
from datetime import datetime
from typing import List, Dict, Any, Optional
from loguru import logger
from shared.models import MarketBar
from data.store import DiskDataStore

# DNSE Field Mapping Table (V1 - Preliminary)
# Since DNSE payload is dynamic, we use this table to normalize to our internal MarketBar.
# Use TODO if a field is uncertain.
TODO_DNSE_MAPPING = {
    "open": "o",       # Assumption: 'o' for open
    "high": "h",       # Assumption: 'h' for high
    "low": "l",        # Assumption: 'l' for low
    "close": "c",      # Assumption: 'c' for close
    "volume": "v",     # Assumption: 'v' for volume
    "timestamp": "t",  # Assumption: 't' for unix timestamp
    "symbol": "s"      # Assumption: 's' for symbol
}

class DnseDataIngestionService:
    """
    Pipeline 1: Research / Data Platform (DNSE)
    Responsible for fetching historical data from DNSE and persisting it for research.
    Note: DNSE is the primary source for historical analysis, NOT execution.
    """
    def __init__(self, store: DiskDataStore, api_key: str = "demo"):
        self.store = store
        self.api_key = api_key
        logger.info("DnseDataIngestionService initialized.")

    async def fetch_history(self, symbol: str, timeframe: str = "1D", limit: int = 100) -> List[MarketBar]:
        """
        Fetches historical bars from DNSE.
        Returns a list of normalized MarketBar objects.
        """
        logger.info(f"DNSE: Fetching history for {symbol} ({timeframe})")
        
        res_map = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "1D": "1D"}
        resolution = res_map.get(timeframe, "1D")
        
        # Calculate timestamps
        to_unix = int(datetime.now().timestamp())
        if resolution in ["1", "5", "15", "60"]:
            from_unix = to_unix - (limit * int(resolution) * 60 * 5) # Buffer
        else:
            from_unix = to_unix - (limit * 86400 * 2) # Buffer
            
        # Determine endpoint based on symbol
        query_symbol = symbol
        endpoint = "stock"
        if symbol.startswith("VN30F"):
            endpoint = "derivative"
            query_symbol = "VN30F1M" # Use continuous contract
        elif symbol in ["VN30", "VN100", "HNX30"]:
            endpoint = "index"
            
        url = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/{endpoint}"
        params = {
            "from": from_unix,
            "to": to_unix,
            "symbol": query_symbol,
            "resolution": resolution
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"DNSE API Error: HTTP {response.status}")
                        return []
                        
                    data = await response.json()
                    if "s" in data and data.get("s") != "ok":
                        logger.error(f"DNSE API Error: Status {data.get('s')}")
                        return []
                        
                    t = data.get("t", [])
                    o = data.get("o", [])
                    h = data.get("h", [])
                    l = data.get("l", [])
                    c = data.get("c", [])
                    v = data.get("v", [])
                    
                    normalized_bars = []
                    for i in range(len(t)):
                        try:
                            bar = MarketBar(
                                symbol=symbol,
                                timeframe=timeframe,
                                timestamp=datetime.fromtimestamp(t[i]),
                                open=float(o[i]),
                                high=float(h[i]),
                                low=float(l[i]),
                                close=float(c[i]),
                                volume=int(v[i]),
                                source="dnse"
                            )
                            normalized_bars.append(bar)
                        except Exception as e:
                            logger.error(f"DNSE Mapping error on index {i}: {e}")
                            
                    return normalized_bars[-limit:] if limit > 0 else normalized_bars
                    
        except Exception as e:
            logger.error(f"DNSE Fetch Exception: {e}")
            return []

    async def backfill_symbol(self, symbol: str, timeframe: str = "1D"):
        """Syncs DNSE history to local DiskDataStore."""
        bars = await self.fetch_history(symbol, timeframe)
        for bar in bars:
            await self.store.save_candle(
                symbol=bar.symbol,
                timestamp=bar.timestamp,
                ohlcv={
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume
                },
                timeframe=timeframe
            )
        logger.success(f"DNSE: Backfilled {len(bars)} bars for {symbol}")
