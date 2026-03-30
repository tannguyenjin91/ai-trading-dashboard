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
        # 1. Fetch Data — 200 bars to ensure enough for all indicators
        print(f"Fetching recent data for {symbol} (15m, limit=200)...")
        bars = await dnse.fetch_history(symbol, timeframe="15m", limit=200)

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
        
        print(f"DataFrame shape: {df.shape}")

        # 3. Call AI
        print("Calling AIReasoningService...")
        insight = await ai_service.generate_market_insight(df)

        if not insight:
            raise Exception("AI failed to generate insight.")

        # 4. Extract fields
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
        atr = insight.get("atr", 0)
        macd_hist = insight.get("macd_hist", 0)
        ema9 = insight.get("ema9", 0)
        ema21 = insight.get("ema21", 0)
        momentum = insight.get("momentum", "N/A")
        ai_source = insight.get("ai_source", "UNKNOWN")
        data_quality = insight.get("data_quality", "unknown")
        missing_indicators = insight.get("missing_indicators", [])
        bars_used = insight.get("bars_used", 0)
        fib_levels = insight.get("fibonacci_levels", [])

        bias_emoji = "\U0001f7e2" if bias == "BULLISH" else ("\U0001f534" if bias == "BEARISH" else "\u26aa")
        s_str = " / ".join(f"{s:,.0f}" for s in supports[:2]) if supports else "N/A"
        r_str = " / ".join(f"{r:,.0f}" for r in resistances[:2]) if resistances else "N/A"
        
        # Data quality badge
        dq_badge = "\u2705 Full" if data_quality == "full" else ("\u26a0\ufe0f Partial" if data_quality == "partial" else "\u274c Price Action Only")
        missing_str = f"\n\u26a0\ufe0f Thi\u1ebfu: {', '.join(missing_indicators)}" if missing_indicators else ""
        
        # Fib display
        fib_str = ""
        if fib_levels:
            key_fibs = [f for f in fib_levels if f.get("level") in [0.236, 0.382, 0.5, 0.618]]
            fib_str = " | ".join(f"Fib{f['level']:.1%}={f['price']:,.1f}" for f in key_fibs)
        if not fib_str:
            fib_str = "Ch\u01b0a \u0111\u1ee7 d\u1eef li\u1ec7u (c\u1ea7n \u226530 n\u1ebfn)"

        print(f"AI Result: {regime} | Bias: {bias} | Confidence: {confidence}%")
        print(f"Data Quality: {data_quality} | Bars: {bars_used} | Missing: {missing_indicators}")
        print(f"RSI: {rsi} | ADX: {adx} | ATR: {atr} | MACD: {macd_hist}")
        print(f"EMA9: {ema9} | EMA21: {ema21}")
        print(f"Supports: {supports} | Resistances: {resistances}")
        print(f"Fib zone: {nearest_fib}")

        # 5. Format rich Telegram message
        msg = (
            f"{bias_emoji} <b>AI Market Summary \u2014 {symbol}</b>\n\n"
            f"<b>{one_liner}</b>\n\n"
            f"\U0001f4ca Gi\u00e1: <code>{current_price:,.1f}</code>  ({price_change_pct:+.2f}%)\n"
            f"\U0001f52d Regime: {regime} | Momentum: {momentum}\n"
            f"\U0001f4c8 Confidence: {confidence}%\n"
            f"\U0001f916 AI Source: {ai_source}\n"
            f"\U0001f4cb Data: {dq_badge} | Bars: {bars_used}\n\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\U0001f6e1 H\u1ed7 tr\u1ee3   : {s_str}\n"
            f"\u26a1 Kh\u00e1ng c\u1ef1 : {r_str}\n"
            f"\U0001f522 Fib       : {fib_str}\n"
            f"\U0001f4cd Fib g\u1ea7n nh\u1ea5t: {nearest_fib}\n\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"RSI: {rsi:.1f} | ADX: {adx:.1f} | ATR: {atr:.1f}\n"
            f"MACD: {macd_hist:.3f} | EMA9: {ema9:.1f} | EMA21: {ema21:.1f}\n\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\U0001f4c8 Bull: {scenario_bull}\n\n"
            f"\U0001f4c9 Bear: {scenario_bear}\n\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\u26a0\ufe0f <i>{risk_note}</i>\n"
            f"{missing_str}"
        )

    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()
        msg = (
            f"\u274c <b>AI TEST FAILED</b>\n\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Error:</b> {str(e)}\n"
            f"<b>Time:</b> {pd.Timestamp.now()}"
        )

    # Send notification
    await notifier.send_message(msg)
    print("Notification sent to Telegram.")

if __name__ == "__main__":
    asyncio.run(main())
