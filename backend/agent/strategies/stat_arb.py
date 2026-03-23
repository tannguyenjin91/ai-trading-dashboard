# backend/agent/strategies/stat_arb.py
# Strategy 6: Statistical Arbitrage on correlated equity pairs
#
# Pairs traded:
#   Steel:  HPG / HSG
#   Bank:   VCB / BID
#   FMCG:   VNM / MCH
#   Energy: GAS / PLX
#
# Logic:
#   zscore = (spread - mean_spread_20) / std_spread_20
#   Entry:  |zscore| > 2.0 → SHORT expensive leg, LONG cheap leg
#   Exit:   |zscore| < 0.5
#
# Phase 1: Stub — implemented in Phase 3.

from .base import Strategy, StrategyConfig

TRADED_PAIRS = [
    ("HPG", "HSG"),   # Steel sector
    ("VCB", "BID"),   # Banking sector
    ("VNM", "MCH"),   # FMCG sector
    ("GAS", "PLX"),   # Energy sector
]


class StatisticalArbitrageStrategy(Strategy):
    """
    Pairs trading using z-score of the price spread.

    Simultaneously goes long the underperforming leg and short
    the outperforming leg when divergence exceeds 2 standard deviations.
    Mean-reverting in nature; profits when the spread normalises.
    """

    @property
    def name(self) -> str:
        return "stat_arb"

    async def generate_signal(self, market_state: dict) -> dict | None:
        """
        TODO (Phase 3):
        1. Calculate spread for all 4 pairs
        2. Compute rolling z-score (window=20)
        3. Signal when |zscore| > 2.0
        4. Return combined signal (both legs)
        """
        raise NotImplementedError("StatisticalArbitrageStrategy — implemented in Phase 3")
