# backend/agent/strategies/vwap.py
# Strategy 3: VWAP Reversion — VN30F scalping (1m–5m)
#
# Logic:
#   Entry: Price deviation from VWAP > ±0.5% AND RSI extreme (>70 short, <30 long)
#   Stop:  Opposite deviation band (e.g. +0.8% from VWAP)
#   Target: VWAP ± 0.1%
#   Time stop: Force close if still open after 20 minutes
#
# Phase 1: Stub — implemented in Phase 3.

from .base import Strategy, StrategyConfig


class VWAPReversionStrategy(Strategy):
    """
    VWAP mean-reversion for VN30F scalping.

    Exploits overextended moves away from the volume-weighted average price.
    High win-rate but small R/R; relies on mean-reversion statistics.
    Mandatory time stop after 20 minutes.
    """

    @property
    def name(self) -> str:
        return "vwap_reversion"

    async def generate_signal(self, market_state: dict) -> dict | None:
        """
        TODO (Phase 3):
        1. Calculate deviation from VWAP
        2. Check RSI extreme condition
        3. Return signal or None
        """
        raise NotImplementedError("VWAPReversionStrategy — implemented in Phase 3")
