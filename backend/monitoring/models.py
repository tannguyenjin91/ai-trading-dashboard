# backend/monitoring/models.py
# SQLAlchemy models for persistent audit logging.

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Text
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class AuditLogEntry(Base):
    """
    Persistent record of every significant event in the trading lifecycle.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    event_type = Column(String(50), nullable=False, index=True) # CYCLE_START, SIGNAL, DECISION, ORDER, FILL, etc.
    symbol = Column(String(20), nullable=True, index=True)
    
    # Execution details
    direction = Column(String(10), nullable=True) # BUY / SELL
    price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=True)
    
    # Agent Logic
    action = Column(String(20), nullable=True) # LONG, SHORT, CLOSE, HOLD
    confidence = Column(Float, nullable=True)
    rationale = Column(Text, nullable=True)
    
    # Metadata
    metadata_json = Column(JSON, nullable=True) # Full payload for debugging

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "symbol": self.symbol,
            "direction": self.direction,
            "price": self.price,
            "quantity": self.quantity,
            "action": self.action,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "metadata": self.metadata_json
        }
