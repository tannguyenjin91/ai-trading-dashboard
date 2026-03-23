# backend/data/vnstock_service.py
import asyncio
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional
from loguru import logger
from vnstock3 import Vnstock
from shared.models import MarketBar
from data.store import DiskDataStore

class VnstockDataIngestionService:
    """
    Pipeline 1: Research / Data Platform
    Responsible for fetching historical data from vnstock3 and persisting it.
    """
    def __init__(self, store: DiskDataStore):
        self.stock = Vnstock()
        self.store = store

    async def backfill_historical_data(
        self, 
        symbol: str, 
        start_date: str, 
        end_date: str, 
        timeframe: str = "1D"
    ) -> int:
        """
        Fetches historical data from vnstock and saves it to the local store.
        Returns the number of bars saved.
        """
        logger.info(f"Backfilling {symbol} from {start_date} to {end_date} ({timeframe})")
        
        try:
            # vnstock3 uses '1D', '1H', '15m', '5m', '1m'
            # Note: Stock price history for derivatives might need different method in vnstock
            df = self.stock.stock_historical_data(
                symbol=symbol, 
                start_date=start_date, 
                end_date=end_date, 
                resolution=timeframe,
                type='stock' # or 'index' / 'derivative'
            )
            
            if df.empty:
                logger.warning(f"No data found for {symbol}")
                return 0

            count = 0
            for _, row in df.iterrows():
                # Normalize time
                ts = row['time'] if 'time' in row else row.name
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
                
                candle = {
                    "open": float(row['open']),
                    "high": float(row['high']),
                    "low": float(row['low']),
                    "close": float(row['close']),
                    "volume": int(row['volume'])
                }
                
                await self.store.save_candle(
                    symbol=symbol,
                    timestamp=ts,
                    ohlcv=candle,
                    timeframe=timeframe
                )
                count += 1
            
            logger.success(f"Successfully backfilled {count} bars for {symbol}")
            return count

        except Exception as e:
            logger.error(f"Vnstock backfill failed for {symbol}: {e}")
            return 0

    async def sync_latest_data(self, symbols: List[str], timeframe: str = "1D"):
        """Syncs the last few days of data for a list of symbols."""
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        for symbol in symbols:
            await self.backfill_historical_data(symbol, start_date, end_date, timeframe)
