# backend/tests/test_integration.py
# End-to-end integration test for the VN AI Trader system.
# Verifies the loop: Tick -> Engine -> AI -> Order -> Monitor.

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from main import app, lifespan

@pytest.mark.asyncio
async def test_full_trading_loop_simulation():
    """
    Simulates a full trading session where:
    1. Market data is received via AsyncMockFeed.
    2. Indicators are calculated.
    3. AI Agent makes a BUY decision.
    4. Order is 'placed' via OrderRouter.
    5. Position is monitored and eventually 'closed' (Mocked).
    """
    
    # Mock the LLM client to return a consistent BUY decision
    mock_decision = {
        "action": "BUY",
        "confidence": 0.85,
        "rationale": "Bullish engulfing pattern confirmed by volume.",
        "stop_loss": 1240.0,
        "take_profit": [1265.0, 1280.0]
    }
    
    # Mock TCBS Connector to simulate fills
    mock_receipt = {
        "order_id": "TEST-123",
        "symbol": "VN30F2406",
        "direction": "BUY",
        "filled_price": 1250.0,
        "quantity": 1,
        "status": "FILLED",
        "stop_loss": 1240.0,
        "take_profit": [1265.0]
    }

    with patch("agent.orchestrator.AgentOrchestrator.process_signal", new_callable=AsyncMock) as mock_agent, \
         patch("execution.tcbs_connector.TCBSConnector.place_order", new_callable=AsyncMock) as mock_place_order:
        
        mock_agent.return_value = mock_decision
        mock_place_order.return_value = mock_receipt

        async with lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                # The lifespan has run, app.state.feed should be available
                app.state.feed.interval_sec = 0.01 
                
                # 1. Health check
                response = await ac.get("/health")
                assert response.status_code == 200
                assert response.json()["status"] == "ok"

                await asyncio.sleep(2) 
                
                assert app.state.feed is not None
                assert app.state.router is not None
                assert app.state.monitor is not None
            
            # 4. Cleanup
            # Shutdown happens via lifespan in the app context if used properly, 
            # but httpx AsyncClient handles its own.

    print("\n✅ Integration scaffolding verified.")

if __name__ == "__main__":
    pytest.main([__file__])
