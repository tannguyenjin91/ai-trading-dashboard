# backend/tests/test_execution.py

import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from execution.tcbs_connector import TcbsBrokerAdapter
from execution.order_router import OrderRouter
from execution.monitor import PositionMonitor

@pytest.fixture
def mock_connector():
    return TcbsBrokerAdapter(paper_mode=True)

@pytest.mark.asyncio
async def test_paper_mode_enforced(mock_connector):
    """Ensure that Paper Mode blocks actual API requests."""
    assert mock_connector.paper_mode is True
    
    receipt = await mock_connector.place_order("VN30F2406", "BUY", 1, 1250.0)
    assert receipt.status.value == "FILLED"
    assert receipt.paper_mode is True

@pytest.mark.asyncio
async def test_execution_blocked_without_paper_mode():
    connector = TcbsBrokerAdapter(paper_mode=False)
    
    from shared.exceptions import RejectError, AuthError
    with pytest.raises((RejectError, AuthError)):
        await connector.place_order("VN30F2406", "BUY", 1, 1250.0)

@pytest.mark.asyncio
async def test_order_router_formats_payload(mock_connector):
    router = OrderRouter(mock_connector)
    decision = {
        "action": "LONG",
        "entry": 1250.0,
        "stop_loss": 1240.0,
        "take_profit": [1280.0]
    }
    
    receipt = await router.route_decision("VN30F", decision)
    assert receipt["stop_loss"] == 1240.0
    assert receipt["take_profit"] == [1280.0]

@pytest.mark.asyncio
async def test_position_monitor_hits_stop_loss(mock_connector):
    monitor = PositionMonitor(mock_connector)
    
    receipt = {
        "order_id": "test-123",
        "symbol": "VN30F",
        "direction": "BUY",
        "quantity": 1.0,
        "filled_price": 1250.0,
        "stop_loss": 1240.0,
        "take_profit": [1280.0]
    }
    
    monitor.register_position(receipt)
    assert len(monitor.active_positions) == 1
    
    # Send a tick that hits stop loss
    with patch.object(mock_connector, 'place_order', new_callable=AsyncMock) as mocked_place:
        await monitor.update_tick("VN30F", 1239.0)
        
        # Monitor should close position (SELL)
        mocked_place.assert_called_once_with(symbol="VN30F", direction="SELL", quantity=1.0, price=1239.0)
        assert len(monitor.active_positions) == 0

@pytest.mark.asyncio
async def test_position_monitor_ignores_unrelated_ticks(mock_connector):
    monitor = PositionMonitor(mock_connector)
    receipt = {
        "order_id": "test-123",
        "symbol": "VN30F",
        "direction": "BUY",
        "quantity": 1.0,
        "filled_price": 1250.0,
        "stop_loss": 1240.0,
        "take_profit": [1280.0]
    }
    monitor.register_position(receipt)
    
    # Send tick that is safe
    with patch.object(mock_connector, 'place_order', new_callable=AsyncMock) as mocked_place:
        await monitor.update_tick("VN30F", 1260.0)
        mocked_place.assert_not_called()
        assert len(monitor.active_positions) == 1
