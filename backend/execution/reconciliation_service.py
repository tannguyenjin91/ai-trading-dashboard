# backend/execution/reconciliation_service.py
from typing import Dict, Any, Optional
from loguru import logger
from datetime import datetime
from shared.models import OrderStateNormalized, FillEvent, SystemEvent
from shared.enums import OrderStatus

class OrderReconciliationService:
    """
    Pipeline 2: Live Trading / Execution
    Source of Truth for Order Life Cycle.
    Maps broker-specific payloads to normalized internal state.
    """
    def __init__(self, notifier: Any = None, audit_logger: Any = None):
        self.notifier = notifier
        self.audit_logger = audit_logger
        self._order_cache: Dict[str, OrderStateNormalized] = {}

    async def handle_broker_update(self, raw_payload: Dict[str, Any]):
        """
        Entry point for TCBS WebSocket order updates.
        """
        try:
            # TCBS Specific Mapping (Example)
            # data = raw_payload.get('data', {})
            # order_status_map = {"8": OrderStatus.FILLED, "2": OrderStatus.REJECTED, ...}
            
            order_id = raw_payload.get('orderId')
            if not order_id:
                return

            status_str = raw_payload.get('status')
            # Normalize status... (Simplified for now)
            status = OrderStatus.FILLED if status_str == 'FILLED' else OrderStatus.PENDING
            
            normalized = OrderStateNormalized(
                order_id=order_id,
                status=status,
                filled_qty=raw_payload.get('filledQty', 0),
                avg_price=raw_payload.get('avgPrice'),
                timestamp=datetime.now()
            )
            
            # 1. Update local cache
            self._order_cache[order_id] = normalized
            
            # 2. Audit Log
            if self.audit_logger:
                await self.audit_logger.log_event("ORDER_UPDATE", normalized.model_dump())
                
            # 3. Notify
            if self.notifier:
                if status == OrderStatus.FILLED:
                    await self.notifier.send_alert(f"<b>ORDER FILLED:</b> {order_id}\nQty: {normalized.filled_qty}", level="INFO")
                elif status == OrderStatus.REJECTED:
                    await self.notifier.send_alert(f"<b>ORDER REJECTED:</b> {order_id}", level="ERROR")

            logger.info(f"Reconciliation: Order {order_id} synced to {status}")

        except Exception as e:
            logger.error(f"Reconciliation failed: {e}")

    def get_order_state(self, order_id: str) -> Optional[OrderStateNormalized]:
        return self._order_cache.get(order_id)

    async def reconcile_positions(self, broker_portfolio: Dict[str, Any], active_positions: list):
        """
        Periodically checks for discrepancies between internal system state and broker truth.
        """
        try:
            if not active_positions:
                return

            logger.debug(f"[Reconciliation] Found {len(active_positions)} active positions at broker.")
            
            # Placeholder for complex discrepancy matching
            for pos in active_positions:
                symbol = pos.get("symbol", "UNKNOWN")
                volume = pos.get("volume", 0)
                if volume != 0:
                    logger.info(f"[Reconciliation] Syncing open position: {symbol} (Vol: {volume})")
                    
        except Exception as e:
            logger.error(f"Periodic reconciliation failed: {e}")
