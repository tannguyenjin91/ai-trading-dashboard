# backend/tests/test_production_safety.py
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock

from shared.models import TradeIntent, OrderReceipt
from shared.enums import TradeAction, RiskStatus, OrderStatus
from execution.execution_service import ExecutionService
from execution.risk_engine import RiskEngine
from execution.tcbs_connector import TcbsBrokerAdapter

@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.live_trading = False
    settings.stale_data_threshold_sec = 60
    settings.duplicate_signal_window_sec = 300
    settings.max_position_size = 5
    settings.environment = "development"
    return settings

def create_test_intent(symbol="VN30F2406", action=TradeAction.BUY, paper_mode=True):
    return TradeIntent(
        strategy_name="TestStrategy",
        symbol=symbol,
        action=action,
        confidence=90.0,
        reason="Test reason",
        timeframe="1m",
        qty=1,
        paper_mode=paper_mode
    )

@pytest.mark.asyncio
async def test_stale_data_rejection(mock_settings):
    # Setup
    risk_engine = RiskEngine(settings=mock_settings)
    broker = AsyncMock(spec=TcbsBrokerAdapter)
    broker.get_portfolio.return_value = {"balance": 100000.0}
    broker.get_positions.return_value = []
    
    execution_service = ExecutionService(broker=broker, risk_engine=risk_engine, notifier=AsyncMock())
    
    intent = create_test_intent()
    
    # 1. Valid data (5s old)
    last_candle_time = datetime.now() - timedelta(seconds=5)
    receipt = await execution_service.execute_intent(intent, last_candle_time=last_candle_time)
    assert receipt is not None
    
    # 2. Stale data (120s old)
    last_candle_time_stale = datetime.now() - timedelta(seconds=120)
    receipt_stale = await execution_service.execute_intent(intent, last_candle_time=last_candle_time_stale)
    assert receipt_stale is None
    execution_service.notifier.send_risk_rejection.assert_called()
    assert "STALE" in execution_service.notifier.send_risk_rejection.call_args[0][1]

@pytest.mark.asyncio
async def test_duplicate_signal_prevention(mock_settings):
    risk_engine = RiskEngine(settings=mock_settings)
    broker = AsyncMock(spec=TcbsBrokerAdapter)
    broker.get_portfolio.return_value = {"balance": 100000.0}
    broker.get_positions.return_value = []
    
    execution_service = ExecutionService(broker=broker, risk_engine=risk_engine, notifier=AsyncMock())
    
    intent = create_test_intent()
    
    # 1. First execution - Success
    await execution_service.execute_intent(intent)
    
    # 2. Immediate second execution - Blocked
    receipt_dup = await execution_service.execute_intent(intent)
    assert receipt_dup is None
    assert "DUPLICATE" in execution_service.notifier.send_risk_rejection.call_args[0][1]

@pytest.mark.asyncio
async def test_live_trading_enforcement(mock_settings):
    mock_settings.live_trading = False # Global switch off
    risk_engine = RiskEngine(settings=mock_settings)
    broker = AsyncMock(spec=TcbsBrokerAdapter)
    broker.get_portfolio.return_value = {"balance": 100000.0}
    broker.get_positions.return_value = []
    
    execution_service = ExecutionService(broker=broker, risk_engine=risk_engine, notifier=AsyncMock())
    
    # Intent with paper_mode=False (Attempting live trade)
    intent = create_test_intent(paper_mode=False)
    
    receipt = await execution_service.execute_intent(intent)
    assert receipt is None
    assert "DISABLED" in execution_service.notifier.send_risk_rejection.call_args[0][1]

@pytest.mark.asyncio
async def test_broker_fetch_failure_handling(mock_settings):
    risk_engine = RiskEngine(settings=mock_settings)
    broker = AsyncMock(spec=TcbsBrokerAdapter)
    broker.get_portfolio.side_effect = Exception("API Connection Timeout")
    
    execution_service = ExecutionService(broker=broker, risk_engine=risk_engine, notifier=AsyncMock())
    intent = create_test_intent()
    
    receipt = await execution_service.execute_intent(intent)
    assert receipt is None
    execution_service.notifier.send_alert.assert_called_with(
        "Execution failed: Could not fetch portfolio for VN30F2406", 
        level="ERROR"
    )
