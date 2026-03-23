# backend/execution/monitor.py
# Real-time position status monitor matching current prices to SL/TP.

import asyncio
from loguru import logger
from typing import Dict, List, Any
from execution.tcbs_connector import TcbsBrokerAdapter

class PositionMonitor:
    """
    Tracks active positions in memory.
    Evaluates new price ticks to trigger automated Stop Loss or Take Profit.
    """
    def __init__(self, connector: TcbsBrokerAdapter, manager=None):
        self.connector = connector
        self.manager = manager
        self.active_positions: List[Dict[str, Any]] = []

    def register_position(self, receipt: dict):
        """Adds a newly filled order to monitoring."""
        if not receipt:
            return
            
        position = {
            "order_id": receipt["order_id"],
            "symbol": receipt["symbol"],
            "direction": receipt["direction"], # BUY implies LONG, SELL implies SHORT
            "entry_price": receipt["filled_price"],
            "quantity": receipt["quantity"],
            "stop_loss": receipt.get("stop_loss"),
            "take_profit": receipt.get("take_profit", [])
        }
        self.active_positions.append(position)
        logger.info(f"🔭 Monitor tracking new position: {position['direction']} {position['symbol']} @ {position['entry_price']} (SL: {position['stop_loss']})")

    async def update_tick(self, symbol: str, current_price: float):
        """
        Called when a new tick arrives.
        Checks if current_price breaches SL or TP for tracked positions.
        """
        to_remove = []
        for pos in self.active_positions:
            if pos["symbol"] != symbol:
                continue

            sl = pos["stop_loss"]
            tps = pos["take_profit"]
            is_long = pos["direction"] == "BUY"
            
            triggered, trigger_reason = False, ""
            
            # Check LONG thresholds
            if is_long:
                if sl and current_price <= sl:
                    triggered, trigger_reason = True, "Stop Loss"
                elif tps and len(tps) > 0 and current_price >= tps[0]:
                    triggered, trigger_reason = True, "Take Profit 1"
            # Check SHORT thresholds
            else:
                if sl and current_price >= sl:
                    triggered, trigger_reason = True, "Stop Loss"
                elif tps and len(tps) > 0 and current_price <= tps[0]:
                    triggered, trigger_reason = True, "Take Profit 1"

            if triggered:
                logger.warning(f"Position trigger [{trigger_reason}] hit for {symbol} at {current_price}!")
                
                # Execute closing order (reverse direction)
                close_dir = "SELL" if is_long else "BUY"
                receipt = await self.connector.place_order(
                    symbol=symbol,
                    direction=close_dir,
                    quantity=pos["quantity"],
                    price=current_price
                )
                
                # Broadcast Closure to Frontend
                if self.manager:
                    await self.manager.broadcast({
                        "type": "DECISION",
                        "data": {
                            "action": "CLOSE",
                            "confidence": 100,
                            "rationale": f"Automatic {trigger_reason} triggered at {current_price}",
                            "symbol": symbol
                        }
                    })
                    await self.manager.broadcast({
                        "type": "POSITION_CLOSED",
                        "data": {"order_id": pos["order_id"], "symbol": symbol}
                    })

                to_remove.append(pos)

        # Cleanup closed positions
        for r in to_remove:
            self.active_positions.remove(r)

