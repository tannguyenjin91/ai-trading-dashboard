from __future__ import annotations

import asyncio
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterable, Optional

import pandas as pd
from loguru import logger

from data.store import DiskDataStore
from shared.models import MarketBar

try:
    from vnstock import Quote
except Exception:  # pragma: no cover - fallback for older local setups
    Quote = None


class VnstockDataIngestionService:
    """
    Signal-mode data provider backed by vnstock.
    Fetches historical bars, latest price, and optionally persists candles locally.
    """

    DEFAULT_SOURCES = ("VCI", "KBS")
    PROXY_ENV_KEYS = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    )
    _proxy_lock = threading.Lock()

    def __init__(self, store: DiskDataStore, default_source: str = "VCI"):
        self.store = store
        self.default_source = default_source.upper()

    def normalize_symbol(self, symbol: str) -> str:
        return (symbol or "").upper().strip()

    async def fetch_history(
        self,
        symbol: str,
        timeframe: str = "1D",
        limit: int = 200,
        start: str | None = None,
        end: str | None = None,
        source: str | None = None,
    ) -> list[MarketBar]:
        df = await self.fetch_history_df(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            start=start,
            end=end,
            source=source,
        )
        if df.empty:
            return []

        bars: list[MarketBar] = []
        for timestamp, row in df.iterrows():
            bars.append(
                MarketBar(
                    symbol=self.normalize_symbol(symbol),
                    timeframe=timeframe,
                    timestamp=timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(float(row.get("volume", 0) or 0)),
                    source="vnstock",
                )
            )
        return bars

    async def fetch_history_df(
        self,
        symbol: str,
        timeframe: str = "1D",
        limit: int = 200,
        start: str | None = None,
        end: str | None = None,
        source: str | None = None,
    ) -> pd.DataFrame:
        normalized_symbol = self.normalize_symbol(symbol)
        if Quote is None:
            logger.warning("vnstock package is unavailable in the current environment.")
            return pd.DataFrame()

        start_str, end_str = self._resolve_range(start=start, end=end, timeframe=timeframe, limit=limit)
        sources = self._source_candidates(source)
        cached_df = await self.store.get_candles_range(
            symbol=normalized_symbol,
            timeframe=timeframe,
            start=start_str,
            end=end_str,
            limit=limit,
        )
        if self._cached_frame_is_sufficient(cached_df, start_str, end_str, limit):
            logger.info(f"Using cached vnstock history for {normalized_symbol} ({timeframe}): {len(cached_df)} bars")
            return cached_df.tail(limit) if limit > 0 else cached_df
        remote_df = pd.DataFrame()

        for candidate in sources:
            try:
                df = await asyncio.to_thread(
                    self._fetch_history_sync,
                    normalized_symbol,
                    candidate,
                    start_str,
                    end_str,
                    timeframe,
                )
                if not df.empty:
                    remote_df = df.tail(limit) if limit > 0 else df
                    await self._persist_dataframe(normalized_symbol, timeframe, remote_df)
                    logger.info(f"vnstock history loaded for {normalized_symbol} via {candidate}: {len(remote_df)} bars")
                    break
            except Exception as exc:
                logger.warning(f"vnstock fetch failed for {normalized_symbol} via {candidate}: {exc}")

        merged = self._merge_frames(cached_df, remote_df)
        if not merged.empty:
            return merged.tail(limit) if limit > 0 else merged

        return pd.DataFrame()

    async def fetch_latest_price(self, symbol: str, source: str | None = None) -> Optional[float]:
        df = await self.fetch_history_df(symbol, timeframe="1m", limit=5, source=source)
        if not df.empty:
            return float(df["close"].iloc[-1])

        fallback = await self.fetch_history_df(symbol, timeframe="1D", limit=2, source=source)
        if not fallback.empty:
            return float(fallback["close"].iloc[-1])
        return None

    async def backfill_historical_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        timeframe: str = "1D",
        source: str | None = None,
    ) -> int:
        df = await self.fetch_history_df(
            symbol=symbol,
            timeframe=timeframe,
            start=start_date,
            end=end_date,
            limit=0,
            source=source,
        )
        if df.empty:
            logger.warning(f"No vnstock data found for {symbol}")
            return 0

        count = 0
        for timestamp, row in df.iterrows():
            await self.store.save_candle(
                symbol=self.normalize_symbol(symbol),
                timestamp=timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp,
                ohlcv={
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(float(row.get("volume", 0) or 0)),
                },
                timeframe=timeframe,
            )
            count += 1

        logger.success(f"Backfilled {count} bars for {symbol} ({timeframe})")
        return count

    async def backfill_recent_data(
        self,
        symbol: str,
        days: int = 30,
        timeframe: str = "1m",
        source: str | None = None,
    ) -> int:
        end_dt = datetime.now()
        if timeframe in {"1m", "5m", "15m", "30m", "1H", "1h"}:
            start_date = (end_dt - timedelta(days=max(days, 1))).strftime("%Y-%m-%d %H:%M:%S")
            end_date = end_dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            start_date = (end_dt - timedelta(days=max(days, 1))).strftime("%Y-%m-%d")
            end_date = end_dt.strftime("%Y-%m-%d")
        return await self.backfill_historical_data(symbol, start_date, end_date, timeframe=timeframe, source=source)

    async def sync_latest_data(self, symbols: Iterable[str], timeframe: str = "1D") -> None:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        for symbol in symbols:
            await self.backfill_historical_data(symbol, start_date, end_date, timeframe)

    def _fetch_history_sync(
        self,
        symbol: str,
        source: str,
        start: str,
        end: str,
        timeframe: str,
    ) -> pd.DataFrame:
        with self._without_proxy_env():
            quote = Quote(symbol=symbol, source=source.lower(), random_agent=False, show_log=False)
            df = quote.history(start=start, end=end, interval=timeframe)
        if df is None or df.empty:
            return pd.DataFrame()
        return self._normalize_dataframe(df)

    async def _persist_dataframe(self, symbol: str, timeframe: str, df: pd.DataFrame) -> None:
        if df.empty:
            return
        for timestamp, row in df.iterrows():
            await self.store.save_candle(
                symbol=symbol,
                timestamp=timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp,
                ohlcv={
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(float(row.get("volume", 0) or 0)),
                },
                timeframe=timeframe,
            )

    @classmethod
    @contextmanager
    def _without_proxy_env(cls):
        saved: dict[str, str] = {}
        with cls._proxy_lock:
            for key in cls.PROXY_ENV_KEYS:
                if key in os.environ:
                    saved[key] = os.environ.pop(key)
            try:
                yield
            finally:
                os.environ.update(saved)

    @staticmethod
    def _merge_frames(cached_df: pd.DataFrame, remote_df: pd.DataFrame) -> pd.DataFrame:
        frames = [frame for frame in (cached_df, remote_df) if not frame.empty]
        if not frames:
            return pd.DataFrame()
        merged = pd.concat(frames)
        merged = merged[~merged.index.duplicated(keep="last")]
        return merged.sort_index()

    @staticmethod
    def _cached_frame_is_sufficient(
        cached_df: pd.DataFrame,
        start: str | None,
        end: str | None,
        limit: int,
    ) -> bool:
        if cached_df.empty:
            return False
        if limit > 0 and len(cached_df) >= limit and not start and not end:
            return True
        if not start and not end:
            return False
        try:
            cached_start = pd.to_datetime(cached_df.index.min())
            cached_end = pd.to_datetime(cached_df.index.max())
            requested_start = pd.to_datetime(start) if start else cached_start
            requested_end = pd.to_datetime(end) if end else cached_end
            if start and len(str(start).strip()) <= 10:
                start_ok = cached_start.date() <= requested_start.date()
            else:
                start_ok = cached_start <= requested_start
            if end and len(str(end).strip()) <= 10:
                end_ok = cached_end.date() >= requested_end.date()
            else:
                end_ok = cached_end >= requested_end
            return start_ok and end_ok
        except Exception:
            return False

    @staticmethod
    def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        rename_map = {
            "time": "timestamp",
            "datetime": "timestamp",
            "Date": "timestamp",
            "date": "timestamp",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
        data = data.rename(columns=rename_map)

        if "timestamp" not in data.columns:
            data = data.reset_index().rename(columns={"index": "timestamp"})

        data["timestamp"] = pd.to_datetime(data["timestamp"])
        for column in ("open", "high", "low", "close", "volume"):
            if column not in data.columns:
                data[column] = 0

        normalized = data[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        normalized = normalized.dropna(subset=["timestamp", "open", "high", "low", "close"])
        normalized["volume"] = normalized["volume"].fillna(0)
        normalized = normalized.sort_values("timestamp").set_index("timestamp")
        return normalized

    def _source_candidates(self, source: str | None) -> list[str]:
        if source:
            primary = source.upper()
            fallbacks = [candidate for candidate in self.DEFAULT_SOURCES if candidate != primary]
            return [primary, *fallbacks]

        fallbacks = [candidate for candidate in self.DEFAULT_SOURCES if candidate != self.default_source]
        return [self.default_source, *fallbacks]

    @staticmethod
    def _resolve_range(
        start: str | None,
        end: str | None,
        timeframe: str,
        limit: int,
    ) -> tuple[str, str]:
        if start and end:
            return start, end

        end_dt = datetime.now()
        if end:
            end_dt = datetime.fromisoformat(end)

        if start:
            return start, end_dt.strftime("%Y-%m-%d %H:%M:%S")

        lookback = max(limit, 1)
        if timeframe == "1m":
            delta = timedelta(minutes=lookback * 2)
        elif timeframe == "5m":
            delta = timedelta(minutes=lookback * 10)
        elif timeframe == "15m":
            delta = timedelta(minutes=lookback * 30)
        elif timeframe in {"1H", "1h"}:
            delta = timedelta(hours=lookback * 2)
        else:
            delta = timedelta(days=max(lookback * 2, 30))

        start_dt = end_dt - delta
        if timeframe in {"1m", "5m", "15m", "30m", "1H", "1h"}:
            return start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S")
        return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")
