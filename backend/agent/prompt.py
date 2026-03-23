# backend/agent/prompt.py
# System prompts and user prompt builders for the Agent Core.
from typing import List, Dict, Any, Optional

SYSTEM_PROMPT = """
Bạn là AI Trading Agent chuyên thị trường chứng khoán Việt Nam (VN30F và Cổ phiếu).

Tư duy kết hợp: Paul Tudor Jones (risk mgmt) + Jesse Livermore (tape reading) + Stanley Druckenmiller (macro timing).

NGUYÊN TẮC BẤT BIẾN:
1. Bảo toàn vốn > mọi thứ khác.
2. Chỉ vào lệnh khi confluence (độ hội tụ tín hiệu) >= 6/10.
3. Không bao giờ risk > 2% NAV/lệnh.
4. Reward/Risk ratio tối thiểu 2:1.

Mỗi quyết định PHẢI có format JSON nghiêm ngặt theo schema sau:
{
  "confluence_score": <int 1-10>,
  "confluence_factors": ["Lý do 1", "Lý do 2"],
  "entry": <float giá vào đề xuất>,
  "stop_loss": <float giá cắt lỗ>,
  "take_profit": [<float tp1>, <float tp2>],
  "confidence": <int 1-100 phần trăm>,
  "action": "LONG" | "SHORT" | "HOLD" | "CLOSE",
  "rationale": "<string giải thích ngắn gọn>"
}
CHỈ TRẢ VỀ JSON HỢP LỆ, KHÔNG TEXT DƯ THỪA.
"""

INSIGHT_SYSTEM_PROMPT = """
Bạn là chuyên gia phân tích kỹ thuật VN30F Futures. Nhiệm vụ của bạn là tạo ra một bản phân tích thị trường
CÓ GIÁ TRỊ THỰC TẾ CHO TRADER, dựa trên dữ liệu kỹ thuật được cung cấp.

QUY TẮC BẮT BUỘC:
1. PHẢI dùng số liệu thật từ context (giá, level, fib, chỉ số). Không bịa số.
2. Các vùng S/R và Fibonacci đã được tính sẵn — hãy dùng chúng, đừng phát minh.
3. Nếu dữ liệu không đủ rõ, hãy nói thẳng trong risk_note thay vì đoán mò.
4. one_liner phải ngắn gọn (1 câu), có số liệu giá cụ thể.
5. scenario phải chỉ rõ vùng giá cụ thể để kích hoạt kịch bản.

CHỈ TRẢ VỀ JSON HỢP LỆ THEO SCHEMA SAU, KHÔNG TEXT DƯ THỪA:
{
  "regime": "TRENDING_UP" | "TRENDING_DOWN" | "CHOPPY" | "VOLATILE",
  "bias": "BULLISH" | "BEARISH" | "NEUTRAL",
  "one_liner": "<1 câu, tiếng Việt, có giá cụ thể>",
  "trend_short": "BULLISH" | "BEARISH" | "NEUTRAL",
  "trend_medium": "BULLISH" | "BEARISH" | "NEUTRAL",
  "momentum": "STRONG" | "MODERATE" | "WEAK",
  "scenario_bullish": "<kịch bản và vùng kích hoạt cụ thể>",
  "scenario_bearish": "<kịch bản và vùng kích hoạt cụ thể>",
  "risk_note": "<cảnh báo hoặc lưu ý rủi ro>",
  "confidence": <int 0-100>
}
"""


def build_trading_prompt(signal_dict: dict, recent_candles: List[Dict[str, Any]]) -> str:
    """
    Constructs the market context from structured signals and a list of recent OHLCV candles with indicators.
    """
    latest_row = recent_candles[-1]

    indicators_str = (
        f"Price: {latest_row['close']:.2f}\n"
        f"RSI (14): {latest_row.get('rsi_14', 0):.2f}\n"
        f"MACD Hist: {latest_row.get('macd_hist', 0):.4f}\n"
        f"ATR (14): {latest_row.get('atr_14', 0):.2f}\n"
        f"ADX (14): {latest_row.get('adx_14', 0):.2f}\n"
        f"VWAP: {latest_row.get('vwap', 0):.2f}\n"
        f"EMA 9: {latest_row.get('ema_9', 0):.2f} / EMA 21: {latest_row.get('ema_21', 0):.2f}\n"
        f"Supertrend Dir: {latest_row.get('supertrend_dir', 0)}\n"
        f"BB Upper: {latest_row.get('bb_upper', 0):.2f} / Lower: {latest_row.get('bb_lower', 0):.2f}"
    )

    history_lines = []
    for i, candle in enumerate(recent_candles):
        history_lines.append(
            f"T-{len(recent_candles)-1-i}: O:{candle['open']:.2f} H:{candle['high']:.2f} L:{candle['low']:.2f} C:{candle['close']:.2f} V:{candle['volume']:.0f}"
        )
    history_str = "\n".join(history_lines)

    prompt = f"""
[MARKET CONTEXT]
Symbol: VN30F (Future Contract)
Recent Candle Sequence (T-0 is most recent):
{history_str}

Latest Indicator Snapshot:
{indicators_str}

[PRE-FILTER SIGNAL]
The deterministic indicator engine generated the following pre-signal:
{signal_dict}

[TASK]
Evaluate the market context and the pre-signal. Consider the price trend over the last {len(recent_candles)} candles.
Decide whether to execute a 'LONG', 'SHORT', 'HOLD', or 'CLOSE' action.
Calculate logical 'stop_loss' and 'take_profit' based on the ATR ({latest_row.get('atr_14', 0):.2f}) and support/resistance mapping.
Ensure RR ratio >= 2. If conditions are choppy, output 'HOLD' with low confidence.
Return ONLY valid JSON.
"""
    return prompt


def build_insight_prompt(
    recent_candles: list,
    sr_levels: Optional[dict] = None,
    fib_data: Optional[dict] = None,
) -> str:
    """
    Constructs a rich market context prompt for the AI market insight.
    Feeds in full indicator snapshot, S/R levels, Fibonacci zones, and price context.
    """
    if not recent_candles:
        return ""

    latest = recent_candles[-1]
    first = recent_candles[0]

    # --- Price Context ---
    current_price = latest.get("close", 0)
    open_price = first.get("open", current_price)
    period_high = max(c.get("high", 0) for c in recent_candles)
    period_low = min(c.get("low", float("inf")) for c in recent_candles)
    price_change = current_price - open_price
    price_change_pct = (price_change / open_price * 100) if open_price else 0

    # --- EMA position ---
    ema9 = latest.get("ema_9", 0)
    ema21 = latest.get("ema_21", 0)
    price_vs_ema9 = "ABOVE" if current_price > ema9 else ("BELOW" if current_price < ema9 else "AT")
    price_vs_ema21 = "ABOVE" if current_price > ema21 else ("BELOW" if current_price < ema21 else "AT")

    # --- Volume context ---
    avg_vol = sum(c.get("volume", 0) for c in recent_candles) / max(len(recent_candles), 1)
    current_vol = latest.get("volume", 0)
    vol_ratio = round(current_vol / avg_vol, 2) if avg_vol > 0 else 1.0
    vol_context = f"{current_vol:,.0f} ({vol_ratio:.2f}x avg)"

    # --- Supertrend direction ---
    st_dir = int(latest.get("supertrend_dir", 0))
    st_label = "BULLISH ▲" if st_dir == 1 else ("BEARISH ▼" if st_dir == -1 else "N/A")

    # --- S/R Levels ---
    sr_str = "Không xác định được"
    if sr_levels:
        supports = sr_levels.get("supports", [])
        resistances = sr_levels.get("resistances", [])
        s_str = ", ".join(f"{s:,.1f}" for s in supports) if supports else "N/A"
        r_str = ", ".join(f"{r:,.1f}" for r in resistances) if resistances else "N/A"
        sr_str = f"Hỗ trợ: {s_str} | Kháng cự: {r_str}"

    # --- Fibonacci ---
    fib_str = "Không có dữ liệu"
    if fib_data and fib_data.get("levels"):
        swing_h = fib_data.get("swing_high", 0)
        swing_l = fib_data.get("swing_low", 0)
        nearest = fib_data.get("nearest_level", "N/A")
        key_fibs = [f for f in fib_data["levels"] if f["level"] in [0.236, 0.382, 0.5, 0.618, 0.786]]
        fib_lines = " | ".join(f"Fib{f['level']:.3f} = {f['price']:,.1f}" for f in key_fibs)
        fib_str = (
            f"Swing High: {swing_h:,.1f} | Swing Low: {swing_l:,.1f}\n"
            f"Các mức Fibonacci: {fib_lines}\n"
            f"Giá hiện tại gần nhất: {nearest}"
        )

    # --- Last 5 candles for sequence ---
    history_lines = []
    for i, c in enumerate(recent_candles[-5:]):
        history_lines.append(
            f"  T-{4-i}: O:{c['open']:.1f} H:{c['high']:.1f} L:{c['low']:.1f} C:{c['close']:.1f} V:{c.get('volume', 0):,.0f}"
        )
    history_str = "\n".join(history_lines)

    prompt = f"""[MARKET CONTEXT — VN30F1M]
Thời gian: {latest.get("timestamp", "N/A")}

=== GIÁ & BIẾN ĐỘNG ===
Giá hiện tại    : {current_price:,.1f}
Thay đổi kỳ     : {price_change:+.1f} ({price_change_pct:+.2f}%)
Đỉnh / Đáy kỳ  : {period_high:,.1f} / {period_low:,.1f}

=== CHỈ SỐ KỸ THUẬT ===
RSI (14)        : {latest.get("rsi_14", 0):.1f}
MACD Hist       : {latest.get("macd_hist", 0):.3f}
ADX (14)        : {latest.get("adx_14", 0):.1f}
ATR (14)        : {latest.get("atr_14", 0):.2f}
Volume          : {vol_context}

EMA 9           : {ema9:.1f}  → Giá {price_vs_ema9} EMA9
EMA 21          : {ema21:.1f}  → Giá {price_vs_ema21} EMA21
Supertrend      : {st_label}
BB Upper / Lower: {latest.get("bb_upper", 0):.1f} / {latest.get("bb_lower", 0):.1f}
VWAP            : {latest.get("vwap", 0):.1f}

=== VÙNG HỖ TRỢ / KHÁNG CỰ ===
{sr_str}

=== FIBONACCI RETRACEMENT ===
{fib_str}

=== 5 NẾN GẦN NHẤT ===
{history_str}

[TASK]
Dựa vào toàn bộ dữ liệu trên, hãy tạo một bản phân tích thị trường ngắn gọn nhưng giàu thông tin.
Chỉ dùng số liệu từ context này. Phân tích bằng tiếng Việt.
Trả về JSON theo đúng schema được yêu cầu.
"""
    return prompt

RECOMMENDATION_SYSTEM_PROMPT = """
Bạn là AI Explainer cho hệ thống Giao Dịch Thuật Toán VN30F.
Hệ thống Kỹ Thuật (Engine) đã tính toán xong các Điểm Vào/Ra/Cắt Lỗ/Xu Hướng bằng toán học cứng.
Nhiệm vụ của bạn là nhận kết quả từ Engine, biên dịch những lý do kỹ thuật khô khan đó thành
những câu văn tự nhiên, mượt mà, và thêm một `risk_note` (lưu ý rủi ro) dưới góc độ một Market Maker/Trader chuyên nghiệp.

QUY TẮC:
1. Bạn KHÔNG ĐƯỢC thay đổi recommendation (BUY/SELL/WAIT).
2. Tóm tắt `reasoning` của Engine thành một đoạn văn súc tích, chuyên nghiệp (dưới 3 câu). Đặt vào mảng `reasoning` (1 phần tử string duy nhất).
3. Sinh ra một câu `risk_note` sắc sảo dựa vào các chỉ báo (ví dụ RSI quá cao rủi ro đảo chiều, chạm Fib quan trọng dễ giật, ADX quá thấp dễ quét 2 đầu). Nếu Engine bảo WAIT, giải thích rõ rủi ro.
4. Trả về đúng JSON cực kỳ đơn giản theo format:
{
  "reasoning": ["<đoạn văn tóm tắt>"],
  "risk_note": "<câu cảnh báo rủi ro>"
}
"""

def build_recommendation_prompt(rec: dict, latest_candle: dict) -> str:
    """Builds prompt for the AI Explainer to narrate the technical recommendation."""
    prompt = f"""[ENGINE OUTPUT]
Symbol: {rec.get('symbol')}
Recommendation: {rec.get('recommendation')}
Bias: {rec.get('bias')} | Confidence: {rec.get('confidence')}%
Current Price: {rec.get('current_price')}
Entry Zone: {rec.get('entry_zone')}
Stop Loss: {rec.get('stop_loss')}
Targets: {rec.get('take_profit_targets')}
Trend: {rec.get('trend_short')} | Momentum: {rec.get('momentum')}
Engine Reasoning (Raw): {rec.get('reasoning')}
Nearest Fib: {rec.get('nearest_fib_zone')}

[MARKET SNAPSHOT]
RSI: {latest_candle.get('rsi_14', 0):.2f} | ADX: {latest_candle.get('adx_14', 0):.2f}
MACD: {latest_candle.get('macd_hist', 0):.3f}
Volume: {latest_candle.get('volume', 0)}

[TASK]
Viết lại mảng reasoning thành 1 đoạn văn (gom vào mảng 1 phần tử) giải thích vì sao Engine cho tín hiệu {rec.get('recommendation')}.
Thêm một risk_note sắc sảo cảnh báo bối cảnh kỹ thuật hiện tại. Trả về JSON.
"""
    return prompt

