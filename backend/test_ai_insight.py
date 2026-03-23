import asyncio
import pandas as pd
from dotenv import load_dotenv

# Load the API keys from .env
load_dotenv() 

from data.dnse_service import DnseDataIngestionService
from strategy_signal.ai_reasoner import AIReasoningService
from config.settings import settings

async def main():
    print(f"Testing AI Insight Generation using {settings.default_ai_model.value}...")
    
    # 1. Fetch Data
    dnse = DnseDataIngestionService(store=None)
    
    symbol = "VN30F1M"
    print(f"Fetching recent data for {symbol}...")
    bars = await dnse.fetch_history(symbol, timeframe="15m", limit=50)
    
    if not bars:
        print("Failed to fetch data from DNSE.")
        return
        
    print(f"Fetched {len(bars)} bars. Latest: {bars[-1].timestamp}")
    
    # 2. Convert to DataFrame
    df_data = []
    for b in bars:
        df_data.append({
            "timestamp": b.timestamp,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume
        })
        
    df = pd.DataFrame(df_data)
    df.set_index("timestamp", inplace=True)
    
    # 3. Call AI
    print("Calling AIReasoningService...")
    ai_service = AIReasoningService()
    insight = await ai_service.generate_market_insight(df)
    
    print("\n" + "="*50)
    print("AI MARKET INSIGHT RESULT")
    print("="*50)
    if insight:
        print(f"REGIME: {insight.get('regime')}")
        print("-" * 50)
        print(insight.get("insight"))
    else:
        print("Failed to generate insight or returned None.")
        
if __name__ == "__main__":
    asyncio.run(main())
