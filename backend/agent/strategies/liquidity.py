# backend/agent/strategies/liquidity.py
# Strategy 4: Liquidity Hunt (Smart Money Concept)
#
# Logic:
#   Sweep: Price runs below a prior swing low then reverses sharply
#   Confirm: Volume > 2× average AND a rejection candle forms
#   Stop:  0.3% below the sweep low (LONG) / above sweep high (SHORT)
#   Target: Previous swing high (LONG) / previous swing low (SHORT)
#
# Phase 1: Stub — implemented in Phase 3.

from .base import Strategy, StrategyConfig


class LiquidityHuntStrategy(Strategy):
    """
    Smart money liquidity sweep detection.

    Identifies stop-hunt moves where institutional traders push price
    below (LONG setup) or above (SHORT setup) swing levels to trigger
    retail stop losses before reversing. High R/R when correctly identified.
    """

    @property
    def name(self) -> str:
        return "liquidity_hunt"

    async def generate_signal(self, market_state: dict) -> dict | None:
        """
        TODO (Phase 3):
        1. Identify recent swing highs/lows
        2. Detect sweep + rejection candle
        3. Confirm with volume
        4. Return signal or None
        """
        raise NotImplementedError("LiquidityHuntStrategy — implemented in Phase 3")
