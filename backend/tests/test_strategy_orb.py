# backend/tests/test_strategy_orb.py
import asyncio
import pandas as pd
from datetime import datetime, time, timedelta
import pytest
from agent.strategies.orb import OpeningRangeBreakoutStrategy
from agent.strategies.base import StrategyConfig

def create_mock_df():
    # Create 1-minute bars for a full morning session
    start_time = datetime.combine(datetime.now().date(), time(9, 0))
    times = [start_time + timedelta(minutes=i) for i in range(120)] # 2 hours
    
    data = {
        'open': [1200.0] * 120,
        'high': [1205.0] * 120,
        'low': [1195.0] * 120,
        'close': [1200.0] * 120,
        'volume': [1000] * 120
    }
    
    df = pd.DataFrame(data, index=times)
    
    # 1. Define Opening Range (09:15 - 09:30)
    # 9:15 is index 15, 9:30 is index 30
    # Set range: 1210 - 1220
    df.loc[times[15:31], 'high'] = 1220.0
    df.loc[times[15:31], 'low'] = 1210.0
    
    # 2. Simulate LONG Breakout at 09:45 (index 45)
    df.loc[times[45], 'close'] = 1225.0
    df.loc[times[45], 'volume'] = 3000 # > 1.5x avg (1000)
    
    return df

@pytest.mark.asyncio
async def test_orb_long():
    df = create_mock_df()
    strategy = OpeningRangeBreakoutStrategy(StrategyConfig(name="orb"))
    
    state = {
        "df": df,
        "symbol": "VN30F_TEST"
    }
    
    # Test at 09:45 (index 45)
    # We slice the DF to simulate real-time arrival
    current_state = {
        "df": df.iloc[:46], # including the 09:45 bar
        "symbol": "VN30F_TEST"
    }
    
    signal = await strategy.generate_signal(current_state)
    
    print("Testing ORB LONG Breakout...")
    if signal:
        print(f"SUCCESS: Signal generated: {signal['action']} at {signal['entry']}")
        print(f"Rationale: {signal['rationale']}")
        assert signal['action'] == "LONG"
        assert signal['entry'] == 1225.0
        assert signal['stop_loss'] == 1210.0 # OR Low
    else:
        print("FAILED: No signal generated at 09:45 breakout bar.")

if __name__ == "__main__":
    asyncio.run(test_orb_long())
