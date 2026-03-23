# backend/api/market_api.py
from fastapi import APIRouter
from typing import Dict, Any
from pydantic import BaseModel
from loguru import logger
from datetime import datetime
import asyncio

from data.store import DiskDataStore
from data.dnse_service import DnseDataIngestionService

router = APIRouter(prefix="/v1/market", tags=["Market Data"])

market_cache = {
    "last_updated": 0,
    "data": None
}

class MarketOverviewResponse(BaseModel):
    symbol: str
    price: float
    change_pct: float
    volume: int
    last_updated: float

@router.get("/overview", response_model=MarketOverviewResponse)
async def get_market_overview(symbol: str = "VN30F1M"):
    """
    Returns the latest market data for a symbol.
    Fetches the latest 2 daily candles to calculate change pct and current price.
    """
    now = datetime.now().timestamp()
    
    # Simple cache: 10 seconds to avoid spamming the DNSE API
    if market_cache["data"] and (now - market_cache["last_updated"] < 10) and market_cache["data"].get("symbol") == symbol:
        return market_cache["data"]
        
    try:
        store = DiskDataStore(db_path="market_data.db")
        dnse = DnseDataIngestionService(store=store)
        
        # Fetch last 2 days to calculate change vs yesterday
        bars = await dnse.fetch_history(symbol, timeframe="1D", limit=2)
        
        if not bars:
            if market_cache["data"]:
                return market_cache["data"]
            return MarketOverviewResponse(symbol=symbol, price=0, change_pct=0, volume=0, last_updated=0)
            
        current_bar = bars[-1]
        
        change_pct = 0.0
        if len(bars) >= 2:
            prev_bar = bars[-2]
            if prev_bar.close > 0:
                change_pct = ((current_bar.close - prev_bar.close) / prev_bar.close) * 100

        result = {
            "symbol": symbol,
            "price": current_bar.close,
            "change_pct": change_pct,
            "volume": current_bar.volume,
            "last_updated": current_bar.timestamp.timestamp()
        }
        
        market_cache["data"] = result
        market_cache["last_updated"] = now
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to fetch market overview: {e}")
        if market_cache["data"]:
            return market_cache["data"]
        return MarketOverviewResponse(symbol=symbol, price=0, change_pct=0, volume=0, last_updated=0)
