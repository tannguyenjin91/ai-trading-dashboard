import asyncio
import pandas as pd
from dotenv import load_dotenv
import os
import sys

# Add backend to path if needed
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from data.dnse_service import DnseDataIngestionService
from strategy_signal.ai_reasoner import AIReasoningService
from monitoring.telegram_bot import TelegramNotifier
from config.settings import settings

async def main():
    print("Initializing services...")
    load_dotenv()

    # Initialize Telegram Notifier
    token = settings.telegram_bot_token.get_secret_value()
    chat_id = settings.telegram_chat_id.get_secret_value()
    notifier = TelegramNotifier(token, chat_id)

    # Initialize AI and Data services
    dnse = DnseDataIngestionService(store=None)
    ai_service = AIReasoningService()

    symbol = "VN30F1M"

    try:
        # 1. Fetch Data
        print(f"Fetching recent data for {symbol}...")
        bars = await dnse.fetch_history(symbol, timeframe="15m", limit=50)

        if not bars:
            raise Exception("Failed to fetch data from DNSE.")

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
        insight = await ai_service.generate_market_insight(df)

        if not insight:
            raise Exception("AI failed to generate insight.")

        # 4. Extract all fields from new MarketSummary schema
        regime = insight.get("regime", "UNKNOWN")
        bias = insight.get("bias", "NEUTRAL")
        confidence = insight.get("confidence", 0)
        one_liner = insight.get("one_liner", "")
        current_price = insight.get("current_price", 0)
        price_change_pct = insight.get("price_change_pct", 0)
        supports = insight.get("supports", [])
        resistances = insight.get("resistances", [])
        nearest_fib = insight.get("nearest_fib_zone", "N/A")
        scenario_bull = insight.get("scenario_bullish", "")
        scenario_bear = insight.get("scenario_bearish", "")
        risk_note = insight.get("risk_note", "")
        rsi = insight.get("rsi", 0)
        adx = insight.get("adx", 0)
        momentum = insight.get("momentum", "N/A")

        bias_emoji = "🟢" if bias == "BULLISH" else ("🔴" if bias == "BEARISH" else "⚪")
        s_str = " / ".join(f"{s:,.0f}" for s in supports[:2]) if supports else "N/A"
        r_str = " / ".join(f"{r:,.0f}" for r in resistances[:2]) if resistances else "N/A"

        print(f"AI Result: {regime} | Bias: {bias} | Confidence: {confidence}%")

        # 5. Format rich Telegram message
        msg = (
            f"{bias_emoji} <b>AI Market Summary — {symbol}</b>\n\n"
            f"<b>{one_liner}</b>\n\n"
            f"📊 Giá: <code>{current_price:,.1f}</code>  ({price_change_pct:+.2f}%)\n"
            f"🔭 Regime: {regime} | Momentum: {momentum}\n"
            f"📈 Confidence: {confidence}%\n\n"
            f"━━━━━━━━━━━━━━\n"
            f"🛡 Hỗ trợ   : {s_str}\n"
            f"⚡ Kháng cự : {r_str}\n"
            f"🔢 Fib zone  : {nearest_fib}\n\n"
            f"━━━━━━━━━━━━━━\n"
            f"📈 Bull: {scenario_bull}\n\n"
            f"📉 Bear: {scenario_bear}\n\n"
            f"━━━━━━━━━━━━━━\n"
            f"⚠️ <i>{risk_note}</i>\n\n"
            f"<i>RSI: {rsi:.1f} | ADX: {adx:.1f} | {bars[-1].timestamp}</i>"
        )

    except Exception as e:
        print(f"Error during test: {e}")
        msg = (
            f"❌ <b>AI TEST FAILED</b>\n\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Error:</b> {str(e)}\n"
            f"<b>Time:</b> {pd.Timestamp.now()}"
        )

    # Send notification
    await notifier.send_message(msg)
    print("Notification sent to Telegram.")

if __name__ == "__main__":
    asyncio.run(main())
