# backend/agent/risk.py
# Risk assessment and position sizing module.
# Implements Kelly Criterion, R/R ratio calculation, and the Decision Gate.
# Phase 1: Stub — implemented in Phase 3.

from dataclasses import dataclass
from loguru import logger


@dataclass
class RiskMetrics:
    """Output from risk assessment for a proposed trade."""
    symbol: str
    direction: str                # "LONG" | "SHORT"
    entry: float
    stop_loss: float
    take_profit: list[float]
    risk_per_share: float         # entry - stop_loss (LONG) or reverse
    reward_per_share: float       # take_profit[0] - entry (LONG) or reverse
    reward_risk: float            # reward / risk
    risk_pct_nav: float           # position risk as % of NAV
    suggested_quantity: int       # Kelly-adjusted shares
    kelly_fraction: float         # raw Kelly fraction (capped at 0.25)
    passes_gate: bool             # True if all hard blocks pass
    block_reasons: list[str]      # List of failed gate conditions


class DecisionGate:
    """
    Mandatory safety filter before any order is placed. Cannot be bypassed.

    HARD_BLOCKS (any one blocks the trade):
    - daily_drawdown >= 3%
    - open_positions_same_dir >= 3
    - risk_per_trade > 2%
    - margin_available < 150%
    - sentiment_score < -0.5
    - time outside 09:15-14:30 (derivatives)
    - confidence < 70%
    - reward_risk < 2.0
    - confluence_score < 6

    CIRCUIT_BREAKERS:
    - 2% drawdown → reduce size 50%
    - 3% drawdown → scalping only
    - 4% drawdown → close positions only
    - 5% drawdown → KILLSWITCH
    """

    HARD_BLOCKS = [
        "daily_drawdown >= 3%",
        "open_positions_same_dir >= 3",
        "risk_per_trade > 2%",
        "margin_available < 150%",
        "sentiment_score < -0.5",
        "time outside 09:15-14:30",
        "confidence < 70%",
        "reward_risk < 2.0",
        "confluence_score < 6",
    ]

    CIRCUIT_BREAKERS = {
        "drawdown_2pct": "reduce_size_50pct",
        "drawdown_3pct": "scalping_only",
        "drawdown_4pct": "close_only",
        "drawdown_5pct": "KILLSWITCH",
    }

    def evaluate(self, decision: dict, portfolio: dict) -> RiskMetrics:
        """
        TODO (Phase 3): Run all hard blocks against the proposed decision.
        Returns RiskMetrics with passes_gate=True/False and reasons.
        """
        raise NotImplementedError("DecisionGate.evaluate() — implemented in Phase 3")


class RiskCalculator:
    """
    Calculates position size using Kelly Criterion, capped at 25%.

    Phase 3 implementation will:
    - Calculate optimal Kelly fraction from win rate and avg R/R
    - Apply drawdown-based size reduction from circuit breakers
    - Ensure NAV risk never exceeds max_risk_per_trade_pct
    """

    def calculate_kelly_size(
        self,
        nav: float,
        entry: float,
        stop_loss: float,
        win_rate: float,
        reward_risk: float,
    ) -> int:
        """
        TODO (Phase 3): Return Kelly-optimal share quantity (integer, >= 1).
        Kelly formula: f = (p * b - q) / b  where b = reward/risk, p=win, q=1-p
        """
        raise NotImplementedError("RiskCalculator.calculate_kelly_size() — implemented in Phase 3")
