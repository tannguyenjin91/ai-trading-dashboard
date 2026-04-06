# backend/data/store.py
# Handles persistent storage of aggregated OHLCV data to a local SQLite database.

from datetime import datetime
from typing import Any, Dict

import aiosqlite
import pandas as pd
from loguru import logger

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

    async def get_candles_range(
        self,
        symbol: str,
        timeframe: str = "1m",
        start: str | None = None,
        end: str | None = None,
        limit: int = 0,
    ) -> pd.DataFrame:
        """Retrieves candles in a time range as a Pandas DataFrame."""
        query = [
            "SELECT timestamp, open, high, low, close, volume",
            "FROM candles",
            "WHERE symbol = ? AND timeframe = ?",
        ]
        params: list[Any] = [symbol, timeframe]
        normalized_start = self._normalize_timestamp_filter(start, is_end=False)
        normalized_end = self._normalize_timestamp_filter(end, is_end=True)

        if normalized_start:
            query.append("AND timestamp >= ?")
            params.append(normalized_start)
        if normalized_end:
            query.append("AND timestamp <= ?")
            params.append(normalized_end)

        if limit and limit > 0:
            query.append("ORDER BY timestamp DESC")
            query.append("LIMIT ?")
            params.append(limit)
        else:
            query.append("ORDER BY timestamp ASC")

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("\n".join(query), tuple(params)) as cursor:
                rows = await cursor.fetchall()
                if not rows:
                    return pd.DataFrame()

        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        return df

    @staticmethod
    def _normalize_timestamp_filter(value: str | None, is_end: bool) -> str | None:
        if not value:
            return None
        try:
            timestamp = pd.to_datetime(value)
            if is_end and len(str(value).strip()) <= 10:
                timestamp = timestamp + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
            return timestamp.isoformat()
        except Exception:
            return value

    async def get_coverage(self, symbol: str, timeframe: str = "1m") -> dict[str, Any]:
        """Returns row count and min/max timestamps for a symbol/timeframe."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT COUNT(*) AS row_count, MIN(timestamp) AS first_ts, MAX(timestamp) AS last_ts
                FROM candles
                WHERE symbol = ? AND timeframe = ?
                """,
                (symbol, timeframe),
            ) as cursor:
                row = await cursor.fetchone()

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "rows": int(row[0] or 0) if row else 0,
            "first_timestamp": row[1] if row else None,
            "last_timestamp": row[2] if row else None,
        }
