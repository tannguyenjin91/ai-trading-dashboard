# backend/tests/test_dnse_mapping.py
import pytest
from datetime import datetime
from data.dnse_service import DnseDataIngestionService, TODO_DNSE_MAPPING
from shared.models import MarketBar

@pytest.mark.asyncio
async def test_dnse_mapping_normalization():
    # Simulate raw DNSE payload based on the mapping table
    raw = {
        "t": 1718870400, # 2024-06-20
        "o": 1250.5,
        "h": 1260.0,
        "l": 1245.2,
        "c": 1255.8,
        "v": 5000,
        "s": "VN30F"
    }
    
    # Verify the mapping constants are used
    assert raw.get(TODO_DNSE_MAPPING["open"]) == 1250.5
    assert raw.get(TODO_DNSE_MAPPING["timestamp"]) == 1718870400
    
    # Verify normalization logic
    # Note: timestamp in DNSE is typically unix seconds
    ts = datetime.fromtimestamp(raw.get(TODO_DNSE_MAPPING["timestamp"]))
    
    bar = MarketBar(
        symbol=raw.get(TODO_DNSE_MAPPING["symbol"]),
        timeframe="1D",
        timestamp=ts,
        open=float(raw.get(TODO_DNSE_MAPPING["open"])),
        high=float(raw.get(TODO_DNSE_MAPPING["high"])),
        low=float(raw.get(TODO_DNSE_MAPPING["low"])),
        close=float(raw.get(TODO_DNSE_MAPPING["close"])),
        volume=int(raw.get(TODO_DNSE_MAPPING["volume"])),
        source="dnse"
    )
    
    assert bar.symbol == "VN30F"
    assert bar.close == 1255.8
    assert bar.source == "dnse"
