# backend/execution/broker_interface.py
from typing import Protocol, Dict, Any, Optional, List, Callable, Awaitable
from shared.models import OrderReceipt, OrderStateNormalized, FillEvent

class BrokerInterface(Protocol):
    """
    Protocol defining the required methods for any broker adapter.
    Ensures the execution layer is decoupled from specific broker APIs (like TCBS).
    """
    async def authenticate(self) -> bool:
        """Authenticate with the broker API."""
        ...

    async def place_order(
        self, 
        symbol: str, 
        direction: str, 
        qty: int, 
        price: Optional[float] = None,
        order_type: str = "MARKET"
    ) -> OrderReceipt:
        """Place a new order and return a standardized receipt."""
        ...

    async def amend_order(
        self,
        order_id: str,
        qty: Optional[int] = None,
        price: Optional[float] = None
    ) -> bool:
        """Modify an existing open order."""
        ...

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        ...

    async def get_portfolio(self) -> Dict[str, Any]:
        """Fetch current balance and open positions."""
        ...

    async def get_balance(self) -> Dict[str, float]:
        """Fetch detailed cash balance (available, pending, etc)."""
        ...

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Fetch detailed open positions."""
        ...

    # --- Streaming Methods ---

    async def stream_market_data(
        self, 
        symbols: List[str], 
        callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Subscribe to real-time market data (ticks/ohlcv)."""
        ...

    async def stream_order_updates(
        self, 
        callback: Callable[[OrderStateNormalized | FillEvent], Awaitable[None]]
    ) -> None:
        """Subscribe to private execution reports (orders, fills)."""
        ...
