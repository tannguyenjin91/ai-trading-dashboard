# backend/data/market_cache.py
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from loguru import logger
from shared.models import LiveMarketSnapshot


class LiveMarketCache:
    """
    Pipeline 2: Live Trading / Execution
    Maintains a high-speed, in-memory snapshot of the live market for symbols.
    Used for pre-execution checks (freshness) and dashboard display.
    """
    def __init__(self, stale_threshold_sec: float = 2.0):
        self._cache: Dict[str, LiveMarketSnapshot] = {}
        self.stale_threshold_sec = stale_threshold_sec
        # Session-level tracking
        self._session_high: Dict[str, float] = {}
        self._session_low: Dict[str, float] = {}
        self._prev_prices: Dict[str, float] = {}

    def update_snapshot(self, symbol: str, price: float, bid: Optional[float] = None, ask: Optional[float] = None, volume: Optional[int] = None, timestamp: Optional[datetime] = None):
        """Updates the local cache with a new market tick."""
        # Track prev price for change calculation
        if symbol in self._cache:
            self._prev_prices[symbol] = self._cache[symbol].price

        self._cache[symbol] = LiveMarketSnapshot(
            symbol=symbol,
            price=price,
            bid=bid,
            ask=ask,
            volume=volume,
            timestamp=timestamp or datetime.now()
        )

        # Session high/low
        if symbol not in self._session_high or price > self._session_high[symbol]:
            self._session_high[symbol] = price
        if symbol not in self._session_low or price < self._session_low[symbol]:
            self._session_low[symbol] = price

    def get_snapshot(self, symbol: str) -> Optional[LiveMarketSnapshot]:
        """Retrieves the latest snapshot for a symbol."""
        snapshot = self._cache.get(symbol)
        if not snapshot:
            return None
        
        # Check for staleness
        elapsed = (datetime.now() - snapshot.timestamp).total_seconds()
        snapshot.is_stale = elapsed > self.stale_threshold_sec
        
        return snapshot

    def is_market_fresh(self, symbol: str) -> bool:
        """Helper to check if a symbol's feed is fresh."""
        snapshot = self.get_snapshot(symbol)
        return snapshot is not None and not snapshot.is_stale

    def get_all_symbols(self) -> List[str]:
        return list(self._cache.keys())

    def get_snapshot_dict(self, symbol: str) -> Optional[dict]:
        """Returns a serializable snapshot dict for API/WebSocket use."""
        snapshot = self.get_snapshot(symbol)
        if not snapshot:
            return None

        prev = self._prev_prices.get(symbol, snapshot.price)
        change = snapshot.price - prev
        change_pct = (change / prev * 100) if prev > 0 else 0

        return {
            "symbol": snapshot.symbol,
            "price": snapshot.price,
            "prev_price": prev,
            "change": round(change, 2),
            "change_pct": round(change_pct, 4),
            "volume": snapshot.volume or 0,
            "high": self._session_high.get(symbol, snapshot.price),
            "low": self._session_low.get(symbol, snapshot.price),
            "bid": snapshot.bid,
            "ask": snapshot.ask,
            "is_stale": snapshot.is_stale,
            "last_updated": snapshot.timestamp.isoformat(),
        }
