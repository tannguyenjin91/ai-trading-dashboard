# backend/tests/test_final_components.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from execution.reconciliation_service import OrderReconciliationService
from data.feature_store import FeatureStoreService
from data.store import DiskDataStore
from shared.models import MarketBar

@pytest.fixture
def mock_notifier():
    notifier = MagicMock()
    notifier.send_message = AsyncMock()
    return notifier

@pytest.fixture
def mock_store():
    store = MagicMock(spec=DiskDataStore)
    store.save_bar = AsyncMock()
    # Mocking get_recent_candles to return a DataFrame for feature store
    import pandas as pd
    import numpy as np
    closes = 100 + 10 * np.sin(np.linspace(0, 4*np.pi, 60))
    store.get_recent_candles = AsyncMock(return_value=pd.DataFrame([
        {"open": c-1, "high": c+2, "low": c-2, "close": c, "volume": 1000}
        for c in closes
    ], index=pd.date_range(end=datetime.now(), periods=60, freq='min')))
    return store

@pytest.mark.asyncio
async def test_order_reconciliation_logic(mock_notifier):
    # Setup reconciler
    reconciler = OrderReconciliationService(notifier=mock_notifier)
    
    # Simulate a TCBS Order Update payload
    tcbs_payload = {
        "orderId": "ORD123",
        "symbol": "VN30F2406",
        "status": "FILLED",
        "avgPrice": 1250.5,
        "filledQty": 5,
        "side": "Buy"
    }
    
    # Process update
    await reconciler.handle_broker_update(tcbs_payload)
    
    # Verify internal state update
    order_state = reconciler.get_order_state("ORD123")
    assert order_state.order_id == "ORD123"
    assert "FILLED" in str(order_state.status)
    assert order_state.avg_price == 1250.5
    
    # Verify Telegram notification was sent via send_alert
    assert mock_notifier.send_alert.called
    args = mock_notifier.send_alert.call_args[0][0]
    assert "ORD123" in args
    assert "FILLED" in args

@pytest.mark.asyncio
async def test_feature_store_calculation(mock_store):
    feature_store = FeatureStoreService(store=mock_store)
    
    symbol = "VN30F"
    # Get the raw data that we mocked to calculate the expected SMA
    df = await mock_store.get_recent_candles(symbol)
    latest_sma = float(df['close'].rolling(window=20).mean().iloc[-1])
    
    vector = await feature_store.calculate_features(symbol, timeframe="1D")
    
    assert vector is not None
    assert vector.symbol == symbol
    assert "rsi_14" in vector.features
    assert "sma_20" in vector.features
    assert vector.features["sma_20"] == pytest.approx(latest_sma, rel=0.01)
