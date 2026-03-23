# backend/tests/test_hybrid_flow.py
import pytest
import asyncio
import sys
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timedelta

# Mock vnstock3 BEFORE importing service
mock_vnstock = MagicMock()
sys.modules["vnstock3"] = mock_vnstock

from shared.models import TradeIntent, MarketBar, LiveMarketSnapshot
from shared.enums import TradeAction, OrderType
from data.market_cache import LiveMarketCache
from strategy_signal.refinement_service import LiveSignalRefinementService
from data.vnstock_service import VnstockDataIngestionService
from data.store import DiskDataStore

@pytest.fixture
def mock_store():
    store = MagicMock(spec=DiskDataStore)
    store.save_candle = AsyncMock()
    return store

@pytest.fixture
def market_cache():
    return LiveMarketCache(stale_threshold_sec=1.0)

@pytest.fixture
def refinement_service(market_cache):
    return LiveSignalRefinementService(cache=market_cache, price_slippage_tolerance=0.01)

@pytest.mark.asyncio
async def test_live_refinement_freshness_guard(refinement_service, market_cache):
    # Test 1: Fresh Data
    symbol = "VN30F2406"
    market_cache.update_snapshot(symbol=symbol, price=1250.0)
    
    intent = TradeIntent(
        strategy_name="test",
        symbol=symbol,
        action=TradeAction.BUY,
        confidence=0.8,
        entry_price=1250.0,
        timeframe="1m",
        reason="test"
    )
    
    is_valid, reason = await refinement_service.refine_intent(intent)
    assert is_valid is True

    # Test 2: Stale Data
    # Manually backdate the snapshot in cache
    market_cache._cache[symbol].timestamp = datetime.now() - timedelta(seconds=5)
    
    is_valid, reason = await refinement_service.refine_intent(intent)
    assert is_valid is False
    assert "Stale" in reason

@pytest.mark.asyncio
async def test_live_refinement_slippage_guard(refinement_service, market_cache):
    symbol = "VN30F2406"
    # Signal says 1250, but live market is already 1270 (> 1% slip)
    market_cache.update_snapshot(symbol=symbol, price=1270.0)
    
    intent = TradeIntent(
        strategy_name="test",
        symbol=symbol,
        action=TradeAction.BUY,
        confidence=0.8,
        entry_price=1250.0,
        timeframe="1m",
        reason="test"
    )
    
    is_valid, reason = await refinement_service.refine_intent(intent)
    assert is_valid is False
    assert "slippage" in reason.lower()

@pytest.mark.asyncio
async def test_vnstock_ingestion_normalization(mock_store):
    service = VnstockDataIngestionService(store=mock_store)
    
    # Mock vnstock response
    import pandas as pd
    mock_df = pd.DataFrame([
        {"time": "2024-06-01 09:00:00", "open": 1250.0, "high": 1255.0, "low": 1248.0, "close": 1252.0, "volume": 1000}
    ])
    service.stock.stock_historical_data = MagicMock(return_value=mock_df)
    
    count = await service.backfill_historical_data("VN30", "2024-06-01", "2024-06-01")
    
    assert count == 1
    assert mock_store.save_candle.called
    args = mock_store.save_candle.call_args[1]
    assert args['symbol'] == "VN30"
    assert args['ohlcv']['close'] == 1252.0
