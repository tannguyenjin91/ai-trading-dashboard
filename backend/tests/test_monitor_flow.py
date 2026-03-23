# backend/tests/test_monitor_flow.py
import pytest
import asyncio
from datetime import datetime
from execution.risk_engine import RiskEngine
from monitoring.system_monitor import SystemMonitor
from shared.models import TradeIntent
from shared.enums import TradeAction, OrderType, RiskStatus

class MockSettings:
    def __init__(self):
        self.live_trading = False
        self.stale_data_threshold_sec = 60
        self.duplicate_signal_window_sec = 300
        self.environment = "development"

@pytest.mark.asyncio
async def test_kill_switch_enforcement():
    settings = MockSettings()
    monitor = SystemMonitor(settings)
    risk_engine = RiskEngine(settings)
    
    intent = TradeIntent(
        symbol="VN30F2406",
        action=TradeAction.BUY,
        entry_price=1250.0,
        qty=1,
        entry_type=OrderType.LIMIT,
        paper_mode=True,
        strategy_name="TestStrategy",
        confidence=85.0,
        reason="Test reason",
        timeframe="1m"
    )
    
    # 1. Normal state
    result = await risk_engine.validate_intent(intent, {"balance": 1000000}, [], monitor=monitor)
    assert result.is_approved is True
    
    # 2. Kill Switch Active
    monitor.toggle_kill_switch(True)
    result = await risk_engine.validate_intent(intent, {"balance": 1000000}, [], monitor=monitor)
    assert result.is_approved is False
    assert "KILL SWITCH" in result.reason

@pytest.mark.asyncio
async def test_live_trading_toggle():
    settings = MockSettings()
    monitor = SystemMonitor(settings)
    risk_engine = RiskEngine(settings)
    
    # Intent is LIVE (paper_mode=False)
    live_intent = TradeIntent(
        symbol="VN30F2406",
        action=TradeAction.BUY,
        entry_price=1250.0,
        qty=1,
        entry_type=OrderType.LIMIT,
        paper_mode=False,
        strategy_name="TestStrategyLive",
        confidence=90.0,
        reason="Test reason live",
        timeframe="1m"
    )
    
    # 1. Monitor has live disabled (default)
    result = await risk_engine.validate_intent(live_intent, {"balance": 1000000}, [], monitor=monitor)
    assert result.is_approved is False
    assert "LIVE TRADING IS DISABLED" in result.reason
    
    # 2. Enable Live via Monitor
    monitor.toggle_live_trading(True)
    result = await risk_engine.validate_intent(live_intent, {"balance": 1000000}, [], monitor=monitor)
    assert result.is_approved is True
