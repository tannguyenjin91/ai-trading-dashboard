# backend/monitoring/performance.py
# Performance tracking: PnL, Sharpe ratio, win rate, max drawdown.
# Calculates metrics from the trade journal persisted in SQLite.
# Phase 1: Stub — implemented in Phase 4.


class PerformanceTracker:
    """
    Computes trading performance metrics from trade history.

    Metrics tracked:
    - Daily / cumulative PnL (VND and %)
    - Win rate (% of profitable trades)
    - Average R multiple (avg_win / avg_loss)
    - Sharpe ratio (annualised, risk-free = 4.5% VN)
    - Max drawdown (from peak NAV)
    - Profit factor (gross_profit / gross_loss)
    - Trade count by strategy

    Phase 4 implementation will query SQLite trade journal
    and compute rolling metrics updated after every closed trade.
    """

    async def get_daily_summary(self, date: str) -> dict:
        """TODO (Phase 4): Return PnL, win rate, and trade count for a given date."""
        raise NotImplementedError("PerformanceTracker.get_daily_summary() — Phase 4")

    async def get_equity_curve(self, days: int = 30) -> list[dict]:
        """TODO (Phase 4): Return time-series of NAV values for equity curve chart."""
        raise NotImplementedError("PerformanceTracker.get_equity_curve() — Phase 4")

    async def calc_sharpe(self, returns: list[float], risk_free: float = 0.045) -> float:
        """TODO (Phase 4): Calculate annualised Sharpe ratio."""
        raise NotImplementedError("PerformanceTracker.calc_sharpe() — Phase 4")
