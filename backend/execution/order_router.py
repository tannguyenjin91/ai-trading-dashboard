# backend/execution/order_router.py
# Order routing logic: position sizing and placement.

from loguru import logger
from typing import Dict, Any, Optional
from execution.tcbs_connector import TcbsBrokerAdapter

class OrderRouter:
    """
    Translates AI Agent JSON decisions into actionable TCBS requests.
    Calculates dynamic quantities based on NAV and risk limits.
    """
    def __init__(self, connector: TcbsBrokerAdapter):
        self.connector = connector

    async def route_decision(self, symbol: str, decision: dict) -> Optional[Dict[str, Any]]:
        """
        Takes LLM parsed dictionary {action, confidence, entry, stop_loss, ...}
        and places it.
        """
        action = decision.get("action", "HOLD").upper()
        
        if action not in ["LONG", "SHORT", "CLOSE"]:
            logger.debug(f"OrderRouter ignoring action: {action}")
            return None
            
        entry_price = decision.get("entry")
        stop_loss = decision.get("stop_loss")
        
        # Calculate dynamic quantity based on risk
        quantity = await self.calculate_quantity(symbol, entry_price, stop_loss)
        
        if quantity <= 0:
            logger.warning(f"OrderRouter skipped {symbol} due to zero/invalid quantity.")
            return None

        try:
            # Map LONG/SHORT to typical execution commands -> BUY/SELL
            direction = "BUY" if action == "LONG" else "SELL"
            
            # Place Order
            logger.info(f"OrderRouter initiating {direction} for {symbol} at target {entry_price} (Qty: {quantity})")
            receipt = await self.connector.place_order(
                symbol=symbol,
                direction=direction,
                qty=int(quantity),
                price=entry_price
            )
            
            # Convert OrderReceipt model to dict for downstream consumers
            result = receipt.model_dump() if hasattr(receipt, 'model_dump') else receipt
            
            # Inject SL and TP from AI into receipt so monitor can track it
            if result:
                result["stop_loss"] = stop_loss
                result["take_profit"] = decision.get("take_profit", [])
                
            return result
            
        except Exception as e:
            logger.error(f"OrderRouter failed to execute {action} on {symbol}: {e}")
            return None

    async def calculate_quantity(self, symbol: str, entry: float, sl: Optional[float]) -> float:
        """
        Calculates position size based on risk settings.
        Simplification: 1 contract for VN30F, or % of NAV for stocks.
        """
        from config.settings import settings
        
        # Default for Paper/MVP
        if "VN30F" in symbol:
            return 1.0 
            
        try:
            portfolio = await self.connector.get_portfolio()
            nav = portfolio.get("balance", 0)
            
            if nav <= 0:
                return 0.0
                
            # If we have a stop loss, use risk-based sizing
            if entry and sl and entry != sl:
                risk_amount = nav * (settings.max_risk_per_trade_pct / 100.0)
                risk_per_share = abs(entry - sl)
                qty = risk_amount / risk_per_share
                return round(max(0, qty), 0)
            
            # Fallback: Use 10% of NAV for buying
            return round((nav * 0.1) / entry, 0) if entry else 0.0
        except Exception as e:
            logger.warning(f"Quantity calculation failed: {e}. Falling back to 1 unit.")
            return 1.0
