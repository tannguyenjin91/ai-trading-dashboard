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
    Used for pre-execution checks (freshness).
    """
    def __init__(self, stale_threshold_sec: float = 2.0):
        self._cache: Dict[str, LiveMarketSnapshot] = {}
        self.stale_threshold_sec = stale_threshold_sec

    def update_snapshot(self, symbol: str, price: float, bid: Optional[float] = None, ask: Optional[float] = None, volume: Optional[int] = None, timestamp: Optional[datetime] = None):
        """Updates the local cache with a new market tick."""
        self._cache[symbol] = LiveMarketSnapshot(
            symbol=symbol,
            price=price,
            bid=bid,
            ask=ask,
            volume=volume,
            timestamp=timestamp or datetime.now()
        )

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
