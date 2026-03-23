# backend/strategy_signal/signal_service.py
import pandas as pd
from loguru import logger
from typing import Optional

from indicators.engine import build_features
from indicators.signals import generate_signals
from .ai_reasoner import AIReasoningService
from shared.models import TradeIntent

class SignalService:
    """
    Coordinates the Strategy Signal Layer.
    Market Data -> Features -> Base Signals -> AI Reasoning -> TradeIntent.
    """
    def __init__(self, ai_service: Optional[AIReasoningService] = None):
        self.ai_service = ai_service or AIReasoningService()

    async def generate_trade_intent(self, symbol: str, df: pd.DataFrame, active_positions_count: int = 0) -> Optional[TradeIntent]:
        """
        Processes market data to produce a validated TradeIntent.
        """
        # 1. Build Features
        features = build_features(df)
        if features is None or features.empty:
            logger.debug(f"Insufficient data to build features for {symbol}")
            return None

        # 2. Generate Base Deterministic Signal
        base_signal = generate_signals(features)
        if not base_signal:
            return None

        # Add symbol to base_signal for AI service
        base_signal["symbol"] = symbol

        # 3. AI Reasoning Gate
        logger.info(f"Base signal triggered for {symbol}: {base_signal['action']}. Consulting AI...")
        trade_intent = await self.ai_service.process_signal(
            pre_signal=base_signal,
            df=features,
            active_positions_count=active_positions_count
        )

        if trade_intent:
            logger.success(f"SignalService produced TradeIntent for {symbol}: {trade_intent.action}")
            return trade_intent

        return None
