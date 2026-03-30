import asyncio
import pandas as pd
from dotenv import load_dotenv
import os
import sys

# Add backend to path if needed
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from data.dnse_service import DnseDataIngestionService
from strategy_signal.recommender import SignalRecommenderEngine
from strategy_signal.ai_reasoner import AIReasoningService
from data.store import DiskDataStore
from config.settings import settings
from monitoring.telegram_bot import TelegramNotifier
from indicators.engine import build_features
from agent.prompt import RECOMMENDATION_SYSTEM_PROMPT, build_recommendation_prompt

load_dotenv()

async def run_test():
    print("🚀 Initializing Signal Recommender Engine Test...")
    store = DiskDataStore("test_db.sqlite3")
    await store.init_db()

    dnse_service = DnseDataIngestionService(store=store, api_key=settings.dnse_api_key.get_secret_value())
    recommender = SignalRecommenderEngine()
    ai_service = AIReasoningService()
    notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token.get_secret_value() if settings.telegram_bot_token else "",
        chat_id=settings.telegram_chat_id.get_secret_value() if settings.telegram_chat_id else ""
    )

    symbol = "VN30F1M"
    print(f"\n📡 Fetching historical data for {symbol} (15m timeframe used in insight, but Engine fetches 1m usually, we will test 15m to get clearer swings)...")
    
    bars = await dnse_service.fetch_history(symbol=symbol, timeframe="15m", limit=100)
    
    if not bars:
        print("❌ Failed to fetch data.")
        return

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

    print(f"✅ Fetched {len(df)} bars. Latest: {df.index[-1]}")

    print("\n⚙️ Running SignalRecommenderEngine (Technical Math)...")
    rec = recommender.generate_recommendation(df, symbol)
    
    if not rec:
        print("❌ Engine returned None.")
        return
        
    print(f"📊 Engine Output: [{rec.recommendation}] | Bias: {rec.bias} | Confidence: {rec.confidence}%")
    if rec.entry_zone:
        print(f"🎯 Entry Zone: {rec.entry_zone.min_price} - {rec.entry_zone.max_price}")
    if rec.stop_loss:
        print(f"🛡 Stop Loss: {rec.stop_loss}")
    if rec.take_profit_targets:
        print(f"🚀 Targets: {rec.take_profit_targets}")
        
    print("📈 Trend:", rec.trend_short)
    print("⚡ Momentum:", rec.momentum)
    print("💬 Raw Reasoning:")
    for r in rec.reasoning:
        print(f"  - {r}")

    print("\n🧠 Sending to AI Explainer for narrative translation...")
    features_df = build_features(df)
    latest_candle = features_df.iloc[-1].to_dict()
    user_prompt = build_recommendation_prompt(rec.model_dump(), latest_candle)
    
    try:
        ai_dict = await ai_service.llm.analyze_market(RECOMMENDATION_SYSTEM_PROMPT, user_prompt)
        if ai_dict:
            print("\n✅ AI Translated Reasoning:")
            raw_reasoning = ai_dict.get("reasoning", [])
            if isinstance(raw_reasoning, list) and len(raw_reasoning) > 0:
                rec.reasoning = raw_reasoning
            elif isinstance(raw_reasoning, str):
                rec.reasoning = [raw_reasoning]
            
            rec.risk_note = ai_dict.get("risk_note", "")
            rec.ai_source = ai_service.llm.provider.upper()
            
            for r in rec.reasoning:
                print(f"  >> {r}")
            print(f"⚠️ Risk Note: {rec.risk_note}")
            
    except Exception as e:
        print(f"❌ AI Explainer failed: {e}")

    # Send Notification
    print("\n📨 Sending to Telegram...")
    emoji = "🟢" if rec.recommendation == "BUY" else ("🔴" if rec.recommendation == "SELL" else "⚪")
    entry_str = f"{rec.entry_zone.min_price:,.1f} - {rec.entry_zone.max_price:,.1f}" if rec.entry_zone else "N/A"
    targets_str = ", ".join([f"{t:,.1f}" for t in rec.take_profit_targets]) if rec.take_profit_targets else "N/A"
    stop_str = f"{rec.stop_loss:,.1f}" if rec.stop_loss else "N/A"
    reason_str = "\n".join(rec.reasoning) if rec.reasoning else "Nội bộ Engine quyết định."
    
    msg = (
        f"{emoji} <b>[TÍN HIỆU] {rec.recommendation} {rec.symbol}</b>\n\n"
        f"📊 <b>Giá hiện tại:</b> <code>{rec.current_price:,.1f}</code>\n"
        f"🎯 <b>Vùng Mua/Bán:</b> {entry_str}\n"
        f"🛡 <b>Stop Loss:</b> {stop_str}\n"
        f"🚀 <b>Take Profit:</b> {targets_str}\n"
        f"📈 <b>Confidence:</b> {rec.confidence}%\n"
        f"🤖 <b>AI Source:</b> {getattr(rec, 'ai_source', 'N/A')}\n\n"
        f"💬 <b>Phân tích:</b> {reason_str}\n\n"
        f"⚠️ <i>Rủi ro: {rec.risk_note}</i>\n"
    )
    await notifier.send_message(msg)
    print("✅ Telegram notification sent!")

if __name__ == "__main__":
    asyncio.run(run_test())
