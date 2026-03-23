# backend/agent/strategies/base.py
# Abstract base class for all trading strategies.
# Every strategy must inherit from Strategy and implement generate_signal().
# Phase 1: Defined here — strategies implemented in Phase 3.

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StrategyConfig:
    """Runtime configuration for a strategy instance."""
    name: str
    enabled: bool = True
    symbols: list[str] | None = None   # None = all symbols
    timeframes: list[str] | None = None


class Strategy(ABC):
    """
    Abstract base class for all vn-ai-trader strategies.

    Subclasses must implement:
    - generate_signal(): analyse market state and return a TradingSignal or None
    - name property

    Optional override:
    - on_position_opened(): called once when agent enters a trade
    - on_position_closed(): called once when agent exits a trade
    """

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable strategy name."""
        ...

    @abstractmethod
    async def generate_signal(self, market_state: dict) -> dict | None:
        """
        Analyse market_state snapshot and return a signal dict or None.

        Returns:
            dict with keys: symbol, direction, entry, stop_loss, take_profit,
                           confluence_score, confluence_factors, notes
            None if no signal this cycle.
        """
        ...

    async def on_position_opened(self, position: dict) -> None:
        """Optional: called when a position based on this strategy is opened."""

    async def on_position_closed(self, position: dict, pnl: float) -> None:
        """Optional: called when a position based on this strategy is closed."""
