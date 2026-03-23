from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from loguru import logger
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from .models import Base, AuditLogEntry

class AuditLogger:
    """
    Append-only audit log stored in SQLite (aiosqlite + SQLAlchemy).
    The audit log is the source of truth for compliance and debugging.
    """

    def __init__(self, db_url: str):
        self.engine = create_async_engine(db_url)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        logger.info(f"AuditLogger initialized with database: {db_url}")

    async def init_db(self):
        """Initializes the database tables if they do not exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.success("AuditLog database tables verified/created.")

    async def log_event(self, event_type: str, symbol: Optional[str] = None, 
                        details: Optional[Dict[str, Any]] = None) -> None:
        """
        Generic event logger.
        """
        details = details or {}
        async with self.session_factory() as session:
            entry = AuditLogEntry(
                event_type=event_type,
                symbol=symbol,
                direction=details.get("direction"),
                price=details.get("price") or details.get("filled_price") or details.get("entry"),
                quantity=details.get("quantity"),
                action=details.get("action"),
                confidence=details.get("confidence"),
                rationale=details.get("rationale") or details.get("reason"),
                metadata_json=details
            )
            session.add(entry)
            await session.commit()
            logger.debug(f"AuditLog successfully persisted {event_type} for {symbol}")

    async def log_cycle(self, cycle_summary: dict) -> None:
        await self.log_event("CYCLE_START", details=cycle_summary)

    async def log_order(self, order_receipt: dict) -> None:
        await self.log_event("ORDER_FILLED", symbol=order_receipt.get("symbol"), details=order_receipt)

    async def log_decision(self, decision: dict) -> None:
        await self.log_event("AI_DECISION", symbol=decision.get("symbol"), details=decision)

    async def query_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Returns most recent N audit entries as a list of dictionaries.
        """
        async with self.session_factory() as session:
            stmt = select(AuditLogEntry).order_by(desc(AuditLogEntry.timestamp)).limit(limit)
            result = await session.execute(stmt)
            entries = result.scalars().all()
            return [e.to_dict() for e in entries]

    async def close(self):
        """Closes the database engine."""
        await self.engine.dispose()
