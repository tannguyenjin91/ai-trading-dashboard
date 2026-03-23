# backend/execution/execution_service.py
from typing import Optional, Dict, Any, List
from loguru import logger
from datetime import datetime

from shared.models import TradeIntent, OrderReceipt, RiskResult
from shared.enums import OrderStatus, RiskStatus
from .broker_interface import BrokerInterface
from .risk_engine import RiskEngine
from strategy_signal.refinement_service import LiveSignalRefinementService

class ExecutionService:
    """
    Coordinates the Broker Execution Layer.
    TradeIntent -> Risk Checks -> Broker Order -> Notifications.
    """
    def __init__(
        self, 
        broker: BrokerInterface, 
        risk_engine: RiskEngine,
        refinement_service: LiveSignalRefinementService,
        notifier: Any = None,
        audit_logger: Any = None
    ):
        self.broker = broker
        self.risk_engine = risk_engine
        self.refinement_service = refinement_service
        self.notifier = notifier
        self.audit_logger = audit_logger

    async def execute_intent(
        self, 
        intent: TradeIntent, 
        last_candle_time: Optional[datetime] = None
    ) -> Optional[OrderReceipt]:
        """
        Processes a TradeIntent through live refinement, risk management, and broker execution.
        """
        logger.info(f"ExecutionService: Processing intent {intent.action} {intent.symbol}")

        # 0. Live Signal Refinement (Pipeline 2 - Last Gate)
        is_fresh, reason = await self.refinement_service.refine_intent(intent)
        if not is_fresh:
            logger.warning(f"Trade REJECTED by LiveRefinement: {reason}")
            await self._notify_error(f"Live Refinement Rejected {intent.symbol}: {reason}")
            return None

        # 1. Fetch current state for Risk Engine
        try:
            portfolio = await self.broker.get_portfolio()
            positions = await self.broker.get_positions()
        except Exception as e:
            logger.error(f"Failed to fetch portfolio/positions for risk check: {e}")
            await self._notify_error(f"Execution failed: Could not fetch portfolio for {intent.symbol}")
            return None

        # 2. Risk Validation
        risk_result: RiskResult = await self.risk_engine.validate_intent(
            intent=intent,
            portfolio=portfolio,
            active_positions=positions,
            monitor=getattr(self, "monitor", None),
            last_candle_time=last_candle_time
        )

        if not risk_result.is_approved:
            logger.warning(f"Trade REJECTED by RiskEngine: {risk_result.reason}")
            await self._notify_risk_rejection(intent, risk_result)
            return None

        # 3. Finalize Order Parameters
        qty = risk_result.adjusted_qty or intent.qty
        if qty <= 0:
            logger.warning(f"Final qty is 0 for {intent.symbol}, skipping execution.")
            return None

        # 4. Execute Order via Broker
        logger.info(f"Risk Approved: Placing {intent.action} {intent.symbol} (Qty: {qty})")
        
        try:
            receipt: OrderReceipt = await self.broker.place_order(
                symbol=intent.symbol,
                direction=str(intent.action.value),
                qty=qty,
                price=intent.entry_price,
                order_type=str(intent.entry_type.value)
            )
        except Exception as e:
            logger.error(f"Broker execution failed: {e}")
            await self._notify_broker_rejection(intent.symbol, str(intent.action.value), str(e))
            return None

        # 5. Audit Logging
        if self.audit_logger:
            await self.audit_logger.log_order(receipt.model_dump())

        # 6. Notifications
        if receipt.status == OrderStatus.FILLED or receipt.status == OrderStatus.SENT:
            await self._notify_execution(receipt, intent)
        else:
            logger.warning(f"Order for {intent.symbol} failed: {receipt.status} - {receipt.message}")
            await self._notify_broker_rejection(intent.symbol, str(intent.action.value), receipt.message or "Unknown failure")

        return receipt

    async def _notify_execution(self, receipt: OrderReceipt, intent: TradeIntent):
        if self.notifier:
            await self.notifier.send_trade_alert(receipt)

    async def _notify_risk_rejection(self, intent: TradeIntent, risk: RiskResult):
        if self.notifier:
            if hasattr(self.notifier, 'send_risk_rejection'):
                await self.notifier.send_risk_rejection(intent, risk.reason or "Unknown Risk")
            else:
                msg = f"<b>RISK REJECTED:</b> {intent.action} {intent.symbol}\nReason: {risk.reason}"
                await self.notifier.send_alert(msg, level="WARNING")

    async def _notify_broker_rejection(self, symbol: str, action: str, error: str):
        if self.notifier:
            if hasattr(self.notifier, 'send_broker_rejection'):
                await self.notifier.send_broker_rejection(symbol, action, error)
            else:
                await self.notifier.send_alert(f"Broker Rejected {action} {symbol}: {error}", level="ERROR")

    async def _notify_error(self, message: str):
        if self.notifier:
            await self.notifier.send_alert(message, level="ERROR")
