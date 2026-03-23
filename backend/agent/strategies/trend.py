# backend/agent/strategies/trend.py
# Strategy 1: Trend Following (15m–1D, equity market)
#
# Logic:
#   Entry: EMA9 > EMA21 > EMA50, RSI in [45, 60], ADX > 25
#   Stop:  2 × ATR below entry (LONG) / above entry (SHORT)
#   Target: 3 × ATR from entry
#
# Phase 1: Stub — implemented in Phase 3.

from .base import Strategy, StrategyConfig


class TrendFollowingStrategy(Strategy):
    """
    Multi-timeframe trend following for Vietnamese equities.

    Signals are only generated when all three conditions align:
    1. Price structure: EMA9 > EMA21 > EMA50 (bullish stack)
    2. Momentum: RSI(14) in 45–60 zone (not overbought, has fuel)
    3. Trend strength: ADX(14) > 25 (trending, not ranging)
    """

    @property
    def name(self) -> str:
        return "trend_following"

    async def generate_signal(self, market_state: dict) -> dict | None:
        """
        TODO (Phase 3): Check EMA stack + RSI + ADX conditions.
        Return signal dict or None.
        """
        raise NotImplementedError("TrendFollowingStrategy — implemented in Phase 3")
