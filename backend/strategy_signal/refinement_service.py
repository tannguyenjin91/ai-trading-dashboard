# backend/strategy_signal/refinement_service.py
from typing import Optional
from loguru import logger
from shared.models import TradeIntent, LiveMarketSnapshot
from data.market_cache import LiveMarketCache

class LiveSignalRefinementService:
    """
    Pipeline 2: Live Trading / Execution
    The 'Final Gate' that validates a strategy signal against live market context.
    Ensures that the price in the signal is still achievable and that the market feed is NOT stale.
    Source of Truth: TCBS Market WebSocket.
    """
    def __init__(self, cache: LiveMarketCache, price_slippage_tolerance: float = 0.005):
        self.cache = cache
        self.price_slippage_tolerance = price_slippage_tolerance

    async def refine_intent(self, intent: TradeIntent) -> tuple[bool, Optional[str]]:
        """
        Validates a TradeIntent against live market reality.
        Returns: (is_valid, rejection_reason)
        """
        snapshot = self.cache.get_snapshot(intent.symbol)
        
        if not snapshot:
            logger.warning(f"Refinement: No live snapshot for {intent.symbol}. Rejection expected.")
            return False, f"Missing live market data for {intent.symbol}"
        
        # 1. Freshness Check (Source of Truth: TCBS WebSocket)
        if snapshot.is_stale:
            logger.error(f"Refinement: Market data for {intent.symbol} is STALE (> {self.cache.stale_threshold_sec}s)")
            return False, "Live Market Data Is Stale. Execution Blocked."

        # 2. Slippage / Price Reality Check
        # If the strategy generated a BUY at 1250, but live market is already at 1260, we might reject.
        if intent.entry_price:
            price_diff = abs(snapshot.price - intent.entry_price) / intent.entry_price
            if price_diff > self.price_slippage_tolerance:
                logger.warning(f"Refinement: Price slippage too high ({price_diff:.2%}) for {intent.symbol}")
                return False, f"Price slippage too high: live={snapshot.price}, signal={intent.entry_price}"

        # 3. Dynamic Thresholds (Optional: e.g., Spread Check)
        if snapshot.bid and snapshot.ask:
            spread = (snapshot.ask - snapshot.bid) / snapshot.price
            if spread > 0.01: # 1% Max spread
                 return False, f"Market spread too wide: {spread:.2%}"

        logger.success(f"Refinement: Intent for {intent.symbol} approved against live context.")
        return True, None
