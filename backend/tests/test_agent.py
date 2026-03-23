# backend/tests/test_agent.py

import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock
from agent.orchestrator import AgentOrchestrator

@pytest.fixture
def mock_signal():
    return {
        "action": "LONG",
        "confidence": 85,
        "reason": "Test Signal",
        "price": 1250.0
    }

@pytest.fixture
def mock_df_row():
    # Create a DataFrame with 20 rows to avoid "Accumulating" warning or errors in rolling averages
    times = [datetime(2024, 6, 1, 10, 0) + timedelta(minutes=i) for i in range(20)]
    data = {
        "open": [1250.0] * 20,
        "high": [1255.0] * 20,
        "low": [1245.0] * 20,
        "close": [1250.0] * 20,
        "volume": [1000] * 20,
        "rsi_14": [40.0] * 20,
        "macd_hist": [2.5] * 20,
        "atr_14": [15.0] * 20,
        "ema_9": [1245.0] * 20,
        "ema_21": [1240.0] * 20,
        "supertrend_dir": [1.0] * 20,
        "bb_upper": [1260.0] * 20,
        "bb_lower": [1230.0] * 20,
        "vwap": [1250.0] * 20,
        "adx_14": [25.0] * 20
    }
    df = pd.DataFrame(data, index=times)
    return df

@pytest.mark.asyncio
async def test_orchestrator_approves_valid_trade(mock_signal, mock_df_row):
    orchestrator = AgentOrchestrator()
    
    mock_decision = {
        "action": "LONG",
        "confidence": 90,
        "entry": 1250.0,
        "stop_loss": 1230.0,
        "take_profit": [1290.0, 1310.0],
        "confluence_score": 8,
        "rationale": "Strong setup"
    }
    
    with patch("agent.llm_client.AIClient.analyze_market", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = mock_decision
        result = await orchestrator.process_signal(mock_signal, mock_df_row)
        
        assert result is not None
        assert result["action"] == "LONG"
        # Risk = 20, Reward = 40, R:R = 2.0 (>= 1.5)

@pytest.mark.asyncio
async def test_orchestrator_rejects_low_confidence(mock_signal, mock_df_row):
    orchestrator = AgentOrchestrator()
    
    mock_decision = {
        "action": "LONG",
        "confidence": 70, # Below 80 threshold
        "entry": 1250.0,
        "stop_loss": 1230.0,
        "take_profit": [1290.0]
    }
    
    with patch("agent.llm_client.AIClient.analyze_market", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = mock_decision
        result = await orchestrator.process_signal(mock_signal, mock_df_row)
        
        assert result is None

@pytest.mark.asyncio
async def test_orchestrator_rejects_bad_risk_reward(mock_signal, mock_df_row):
    orchestrator = AgentOrchestrator()
    
    mock_decision = {
        "action": "LONG",
        "confidence": 85,
        "entry": 1250.0,
        "stop_loss": 1200.0, # Risk 50
        "take_profit": [1260.0]  # Reward 10 -> R:R 0.2
    }
    
    with patch("agent.llm_client.AIClient.analyze_market", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = mock_decision
        result = await orchestrator.process_signal(mock_signal, mock_df_row)
        
        assert result is None
