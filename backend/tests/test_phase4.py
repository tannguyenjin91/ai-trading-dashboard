import pytest
import os
import asyncio
from loguru import logger
from monitoring.audit_log import AuditLogger
from config.settings import settings

@pytest.mark.asyncio
async def test_audit_persistence():
    # Use a temporary test database
    test_db = "sqlite+aiosqlite:///./test_audit.db"
    logger = AuditLogger(test_db)
    
    print("Initializing test database...")
    await logger.init_db()
    
    print("Logging dummy events...")
    await logger.log_cycle({"test": "data"})
    await logger.log_decision({
        "symbol": "VN30F",
        "action": "LONG",
        "confidence": 0.85,
        "rationale": "Test rationale"
    })
    
    print("Querying recent entries...")
    entries = await logger.query_recent(limit=5)
    
    assert len(entries) >= 2
    print(f"Verified: Found {len(entries)} entries in audit log.")
    for e in entries:
        print(f" - [{e['event_type']}] {e['symbol']} {e['action']}")

    await logger.close()
    
    # Cleanup
    if os.path.exists("test_audit.db"):
        os.remove("test_audit.db")
    print("Cleanup successful.")

if __name__ == "__main__":
    asyncio.run(test_audit_persistence())
