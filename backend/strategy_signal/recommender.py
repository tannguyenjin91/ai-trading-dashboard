# backend/strategy_signal/recommender.py
# Technical rule engine that evaluates market data to generate trading recommendations.

import pandas as pd
from typing import Optional, Tuple, List
from loguru import logger
from datetime import datetime

from indicators.engine import build_features, calculate_support_resistance, calculate_fibonacci
from shared.models import SignalRecommendation, EntryZone

class SignalRecommenderEngine:
    """
    Evaluates raw OHLCV and technical features to generate a deterministic 
    SignalRecommendation based on strict technical rules.
    """

    def __init__(self):
        # Configuration thresholds
        self.atr_buffer_mult = 1.0
        self.min_rr_ratio = 1.5

    def _find_closest_levels(self, current_price: float, supports: List[float], resistances: List[float]) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """
        Finds immediate and next support/resistance levels relative to current_price.
        Returns: (immediate_sup, next_sup, immediate_res, next_res)
        """
        sups_below = sorted([s for s in supports if s < current_price], reverse=True)
        res_above = sorted([r for r in resistances if r > current_price])

        imm_sup = sups_below[0] if len(sups_below) > 0 else None
        next_sup = sups_below[1] if len(sups_below) > 1 else imm_sup
        
        imm_res = res_above[0] if len(res_above) > 0 else None
        next_res = res_above[1] if len(res_above) > 1 else imm_res

        return imm_sup, next_sup, imm_res, next_res

    def generate_recommendation(self, df: pd.DataFrame, symbol: str = "VN30F1M") -> Optional[SignalRecommendation]:
        """
        Core rule engine pipeline.
        Returns a structured recommendation based entirely on technical math.
        """
        if df is None or len(df) < 50:
            logger.warning(f"Not enough data to run SignalRecommenderEngine for {symbol}")
            return None

        # 1. Feature Extraction
        features = build_features(df)
        last_bar = features.iloc[-1]
        
        curr_price = float(last_bar["close"])
        ema9 = float(last_bar.get("ema_9", 0))
        ema21 = float(last_bar.get("ema_21", 0))
        macd = float(last_bar.get("macd_hist", 0))
        rsi = float(last_bar.get("rsi_14", 50))
        adx = float(last_bar.get("adx_14", 0))
        atr = float(last_bar.get("atr_14", 1.0))
        supertrend = int(last_bar.get("supertrend_dir", 0))

        # Context Calculations
        sr_data = calculate_support_resistance(features, lookback=20)
        fib_data = calculate_fibonacci(features, lookback=30)
        supports = sr_data.get("supports", [])
        resistances = sr_data.get("resistances", [])
        
        imm_sup, next_sup, imm_res, next_res = self._find_closest_levels(curr_price, supports, resistances)

        # 2. Trend & Bias Evaluation
        # Short trend
        is_uptrend_short = ema9 > ema21 and curr_price > ema9
        is_downtrend_short = ema9 < ema21 and curr_price < ema9
        trend_short = "BULLISH" if is_uptrend_short else ("BEARISH" if is_downtrend_short else "NEUTRAL")

        momentum = "STRONG" if adx >= 25 else ("MODERATE" if adx >= 15 else "WEAK")
        
        bias = "NEUTRAL"
        if trend_short == "BULLISH" and macd > 0 and supertrend == 1:
            bias = "BULLISH"
        elif trend_short == "BEARISH" and macd < 0 and supertrend == -1:
            bias = "BEARISH"

        # 3. Rule Engine for Signal (BUY/SELL/HOLD/WAIT)
        recommendation = "WAIT"
        reasoning = []
        entry_min, entry_max = curr_price, curr_price
        stop_loss = None
        targets = []
        confidence = 0.0

        if bias == "BULLISH":
            reasoning.append("Xu hướng ngắn hạn đang TĂNG (EMA9 cắp lên EMA21, Supertrend xanh).")
            # Check pullback condition vs breakout condition
            if imm_sup and (curr_price - imm_sup) <= (atr * 1.5):
                recommendation = "BUY"
                reasoning.append(f"Giá đang trong nhịp điều chỉnh gần vùng hỗ trợ {imm_sup:,.1f}.")
                entry_min, entry_max = imm_sup, curr_price
                stop_loss = imm_sup - (atr * self.atr_buffer_mult)
                if imm_res: targets.append(imm_res)
                if next_res and next_res != imm_res: targets.append(next_res)
                confidence = min(80 + (adx), 95) if rsi < 70 else 60
            elif rsi < 65 and adx > 20: 
                recommendation = "BUY"
                reasoning.append("Momentum tăng ổn định, có thể tiếp diễn xu hướng.")
                entry_min, entry_max = curr_price - (atr*0.5), curr_price
                stop_loss = ema21 - atr
                if imm_res: targets.append(imm_res)
                confidence = 70
            else:
                reasoning.append("Đang trong uptrend nhưng setup chưa đủ an toàn (RSI quá cao hoặc xa hỗ trợ).")
                recommendation = "WAIT"

        elif bias == "BEARISH":
            reasoning.append("Xu hướng ngắn hạn đang GIẢM (EMA9 cắt xuống EMA21, Supertrend đỏ).")
            if imm_res and (imm_res - curr_price) <= (atr * 1.5):
                recommendation = "SELL"
                reasoning.append(f"Giá đang trong nhịp hồi phục kiểm chứng lại kháng cự {imm_res:,.1f}.")
                entry_min, entry_max = curr_price, imm_res
                stop_loss = imm_res + (atr * self.atr_buffer_mult)
                if imm_sup: targets.append(imm_sup)
                if next_sup and next_sup != imm_sup: targets.append(next_sup)
                confidence = min(80 + (adx), 95) if rsi > 30 else 60
            elif rsi > 35 and adx > 20:
                recommendation = "SELL"
                reasoning.append("Momentum giảm ổn định, có thể tiếp diễn nhịp rơi.")
                entry_min, entry_max = curr_price, curr_price + (atr*0.5)
                stop_loss = ema21 + atr
                if imm_sup: targets.append(imm_sup)
                confidence = 70
            else:
                reasoning.append("Đang trong downtrend nhưng vùng giá chưa an toàn để mở vị thế (RSI quá bán hoặc rủi ro giật ngược).")
                recommendation = "WAIT"
        else:
            if momentum == "WEAK":
                reasoning.append(f"Thị trường đi ngang (ADX = {adx:.1f}), chưa rõ xu hướng.")
                recommendation = "HOLD"
            else:
                reasoning.append("Các chỉ báo đang mâu thuẫn, tốt nhất nên đứng ngoài quan sát thêm.")
                recommendation = "WAIT"

        # Add Fib context to reasoning
        nearest_fib = fib_data.get("nearest_level", "")
        if recommendation in ["BUY", "SELL"] and nearest_fib:
            reasoning.append(f"Vùng giá hiện tại đang gần sát mức Fibonacci {nearest_fib}.")

        # Calculate Risk/Reward
        rr_ratio = 0.0
        if recommendation in ["BUY", "SELL"] and stop_loss and targets:
            avg_entry = sum([entry_min, entry_max]) / 2
            risk = abs(avg_entry - stop_loss)
            reward = abs(targets[0] - avg_entry)
            if risk > 0:
                rr_ratio = reward / risk
                
            if rr_ratio < self.min_rr_ratio and recommendation != "WAIT":
                # Downgrade if RR is poor
                recommendation = "WAIT"
                reasoning.append(f"Risk/Reward dự kiến kém ({rr_ratio:.2f} < {self.min_rr_ratio}), hủy tín hiệu.")
                confidence -= 20

        # Construct structured model
        rec = SignalRecommendation(
            symbol=symbol,
            timeframe="15m",
            recommendation=recommendation,
            bias=bias,
            confidence=round(confidence, 1),
            current_price=round(curr_price, 1),
            entry_zone=EntryZone(min_price=round(entry_min,1), max_price=round(entry_max,1)) if recommendation in ["BUY", "SELL"] else None,
            stop_loss=round(stop_loss, 1) if stop_loss else None,
            take_profit_targets=[round(t, 1) for t in targets],
            supports=[round(s, 1) for s in supports],
            resistances=[round(r, 1) for r in resistances],
            nearest_fib_zone=nearest_fib,
            trend_short=trend_short,
            momentum=momentum,
            risk_reward_estimate=round(rr_ratio, 2),
            reasoning=reasoning,
            data_status="live",
            generated_at=datetime.now()
        )

        logger.info(f"SignalRecommenderEngine output: {rec.recommendation} | Confidence {rec.confidence}%")
        return rec
