# backend/data/normalizer.py
# Transforms raw incoming JSON ticks into structured Pydantic models.

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class TickData(BaseModel):
    """
    Represents a single trade or quote event (tick data).
    Matches the standard structure expected by the technical indicator engine.
    """
    symbol: str = Field(description="Ticker symbol, e.g., VN30F2406")
    price: float = Field(description="Last traded price or mid-price")
    volume: float = Field(default=0.0, description="Traded volume for this tick")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC Timestamp of the tick")
    is_buyer_maker: Optional[bool] = Field(default=None, description="True if order was sell, False if buy")

    # Pydantic v2 handles datetime serialization natively via mode="json"


def parse_raw_tick(raw_data: dict) -> list[TickData]:
    """
    Parses a raw dictionary (from a WebSocket or mock feed) into a list of TickData.
    Returns a list because some feeds batch ticks.
    """
    ticks = []

    # Handle standard mock format: {"symbol": "...", "price": 1250.5, "volume": 10, "timestamp": "..."}
    if "symbol" in raw_data and "price" in raw_data:
        try:
            ts = raw_data.get("timestamp")
            if ts and isinstance(ts, str):
                parsed_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            else:
                parsed_ts = datetime.now(timezone.utc)

            tick = TickData(
                symbol=raw_data["symbol"],
                price=float(raw_data["price"]),
                volume=float(raw_data.get("volume", 0.0)),
                timestamp=parsed_ts,
                is_buyer_maker=raw_data.get("is_buyer_maker")
            )
            ticks.append(tick)
        except Exception as e:
            # In a real app we'd log this using loguru
            pass

    return ticks

