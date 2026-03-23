# backend/data/store.py
# Handles persistent storage of aggregated OHLCV data to a local SQLite database.

import aiosqlite
import pandas as pd
from datetime import datetime
from loguru import logger
from typing import List, Dict, Any

class DiskDataStore:
    """
    Saves aggregated OHLCV candles to SQLite.
    Provides basic query capabilities for backtesting or reporting.
    """
    def __init__(self, db_path: str = "market_data.db"):
        self.db_path = db_path

    async def init_db(self):
        """Initializes the SQLite schema."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS candles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    timeframe TEXT,
                    UNIQUE(symbol, timestamp, timeframe)
                )
            """)
            await db.commit()
            logger.info(f"DiskDataStore initialized at {self.db_path}")

    async def save_candle(self, symbol: str, timestamp: datetime, ohlcv: Dict[str, float], timeframe: str = "1m"):
        """Saves a single aggregated candle."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("""
                    INSERT OR REPLACE INTO candles (symbol, timestamp, open, high, low, close, volume, timeframe)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    symbol,
                    timestamp.isoformat(),
                    ohlcv.get("open"),
                    ohlcv.get("high"),
                    ohlcv.get("low"),
                    ohlcv.get("close"),
                    ohlcv.get("volume"),
                    timeframe
                ))
                await db.commit()
            except Exception as e:
                logger.error(f"Failed to save candle to disk: {e}")

    async def get_recent_candles(self, symbol: str, limit: int = 100, timeframe: str = "1m") -> pd.DataFrame:
        """Retrieves recent candles as a Pandas DataFrame."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT timestamp, open, high, low, close, volume 
                FROM candles 
                WHERE symbol = ? AND timeframe = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (symbol, timeframe, limit)) as cursor:
                rows = await cursor.fetchall()
                if not rows:
                    return pd.DataFrame()
                
                df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df = df.set_index("timestamp").sort_index()
                return df
