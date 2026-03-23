# backend/tests/test_new_flow.py
import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

from shared.models import TradeIntent, OrderReceipt, RiskResult
from shared.enums import TradeAction, OrderStatus, RiskStatus
from strategy_signal.signal_service import SignalService
from execution.execution_service import ExecutionService
from execution.risk_engine import RiskEngine
from execution.tcbs_connector import TcbsBrokerAdapter

@pytest.mark.asyncio
async def test_full_trading_flow_success():
    # 1. Setup Mock Broker
    broker = TcbsBrokerAdapter(paper_mode=True)
    await broker.authenticate()
    
    # 2. Setup Risk Engine
    settings = MagicMock()
    settings.environment = "development"
    settings.max_position_size = 10
    risk_engine = RiskEngine(settings=settings)
    
    # 3. Setup Execution Service
    notifier = AsyncMock()
    execution_service = ExecutionService(
        broker=broker,
        risk_engine=risk_engine,
        notifier=notifier
    )
    
    # 4. Create a TradeIntent (Simulating SignalService output)
    intent = TradeIntent(
        strategy_name="TestStrategy",
        symbol="VN30F2406",
        action=TradeAction.BUY,
        confidence=90.0,
        reason="Test reason",
        timeframe="1m"
    )
    
    # 5. Execute
    receipt = await execution_service.execute_intent(intent)
    
    # 6. Verify
    assert receipt is not None
    assert receipt.status == OrderStatus.FILLED
    assert receipt.symbol == "VN30F2406"
    assert receipt.action == TradeAction.BUY
    assert receipt.qty == 1 # Default for VN30F in risk engine
    
    # Verify notification was called
    notifier.send_trade_alert.assert_called_once()
    logger_calls = [call for call in notifier.send_alert.call_args_list]
    # No risk rejection alerts should have been sent
    assert not any("RISK REJECTED" in call.args[0] for call in logger_calls)

@pytest.mark.asyncio
async def test_risk_rejection_flow():
    # 1. Setup Mock Broker with an active position
    broker = AsyncMock(spec=TcbsBrokerAdapter)
    broker.get_portfolio.return_value = {"balance": 100000000.0}
    broker.get_positions.return_value = [{"symbol": "VN30F2406"}] # Active position
    
    # 2. Setup Risk Engine
    settings = MagicMock()
    settings.environment = "development"
    risk_engine = RiskEngine(settings=settings)
    
    # 3. Setup Execution Service
    notifier = AsyncMock()
    execution_service = ExecutionService(
        broker=broker,
        risk_engine=risk_engine,
        notifier=notifier
    )
    
    # 4. Create Intent for same symbol
    intent = TradeIntent(
        strategy_name="TestStrategy",
        symbol="VN30F2406",
        action=TradeAction.BUY,
        confidence=95.0,
        reason="Duplicate signal",
        timeframe="1m"
    )
    
    # 5. Execute
    receipt = await execution_service.execute_intent(intent)
    
    # 6. Verify Rejection
    assert receipt is None
    notifier.send_alert.assert_called()
    # Check if risk rejection notification was sent
    last_alert = notifier.send_alert.call_args.args[0]
    assert "RISK REJECTED" in last_alert
    assert "ALREADY HAVE ACTIVE POSITION" in last_alert
