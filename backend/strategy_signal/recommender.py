# backend/strategy_signal/recommender.py
# Technical rule engine that evaluates market data to generate trading recommendations.

import pandas as pd
from typing import Optional, Tuple, List
from loguru import logger
from datetime import datetime

from indicators.engine import build_features, calculate_atr, calculate_support_resistance, calculate_fibonacci
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
        self.trailing_stop_timeframe = "10min"
        self.trailing_stop_atr_period = 14
        self.trailing_stop_atr_multiplier = 2.0

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

    def _build_trailing_stop_plan(self, df_1m: pd.DataFrame, current_price: float) -> tuple[float, float]:
        df_10m = (
            df_1m.resample(self.trailing_stop_timeframe)
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .dropna()
        )
        atr_value = None
        if len(df_10m) >= self.trailing_stop_atr_period:
            atr_series = calculate_atr(df_10m, self.trailing_stop_atr_period).dropna()
            if not atr_series.empty:
                atr_value = float(atr_series.iloc[-1])
        if atr_value is None or atr_value <= 0:
            atr_value = current_price * 0.0035
        trailing_offset = max(atr_value * self.trailing_stop_atr_multiplier, current_price * 0.003)
        return round(atr_value, 1), round(trailing_offset, 1)

    def generate_recommendation(
        self, df_1m: pd.DataFrame, df_5m: pd.DataFrame, df_15m: pd.DataFrame, symbol: str = "VN30F1M"
    ) -> Optional[SignalRecommendation]:
        """
        Core rule engine pipeline.
        Returns a structured recommendation based entirely on technical math across 3 timeframes.
        - 15m: Bias
        - 5m: Setup
        - 1m: Timing
        """
        if any(df is None for df in [df_1m, df_5m, df_15m]) or len(df_1m) < 50 or len(df_15m) < 10:
            logger.warning(f"Not enough data to run MTF SignalRecommenderEngine for {symbol}")
            return None

        # 1. Feature Extraction on all Timeframes
        f_1m = build_features(df_1m)
        f_5m = build_features(df_5m)
        f_15m = build_features(df_15m)
        
        last_1m = f_1m.iloc[-1]
        last_5m = f_5m.iloc[-1]
        last_15m = f_15m.iloc[-1]
        
        curr_price = float(last_1m["close"])
        
        # --- 15m (Bias) ---
        ema9_15m = float(last_15m.get("ema_9", 0))
        ema21_15m = float(last_15m.get("ema_21", 0))
        macd_15m = float(last_15m.get("macd_hist", 0))
        supertrend_15m = int(last_15m.get("supertrend_dir", 0))
        
        is_uptrend_15m = ema9_15m > ema21_15m and curr_price > ema9_15m
        is_downtrend_15m = ema9_15m < ema21_15m and curr_price < ema9_15m
        
        mtf_bias = "NEUTRAL"
        if is_uptrend_15m and macd_15m > 0 and supertrend_15m == 1:
            mtf_bias = "BULLISH"
        elif is_downtrend_15m and macd_15m < 0 and supertrend_15m == -1:
            mtf_bias = "BEARISH"
            
        # --- 5m (Setup) ---
        ema9_5m = float(last_5m.get("ema_9", 0))
        ema21_5m = float(last_5m.get("ema_21", 0))
        atr_5m = float(last_5m.get("atr_14", 1.0))
        
        # Build Context from 15m and 5m
        sr_data_15m = calculate_support_resistance(f_15m, lookback=20)
        fib_data_15m = calculate_fibonacci(f_15m, lookback=30)
        supports = sr_data_15m.get("supports", [])
        resistances = sr_data_15m.get("resistances", [])
        
        imm_sup, next_sup, imm_res, next_res = self._find_closest_levels(curr_price, supports, resistances)
        
        mtf_setup = "NEUTRAL"
        # Setup checks: Are we bouncing off 15m support or testing 5m ema21?
        if mtf_bias == "BULLISH":
            if imm_sup and (curr_price - imm_sup) <= (atr_5m * 1.5):
                mtf_setup = "PULLBACK_SUPPORT"
            elif ema9_5m > ema21_5m and curr_price >= ema9_5m:
                mtf_setup = "TREND_CONTINUATION"
        elif mtf_bias == "BEARISH":
            if imm_res and (imm_res - curr_price) <= (atr_5m * 1.5):
                mtf_setup = "PULLBACK_RESISTANCE"
            elif ema9_5m < ema21_5m and curr_price <= ema9_5m:
                mtf_setup = "TREND_CONTINUATION"
                
        # --- 1m (Timing) ---
        adx_1m = float(last_1m.get("adx_14", 0))
        rsi_1m = float(last_1m.get("rsi_14", 50))
        macd_1m = float(last_1m.get("macd_hist", 0))
        
        mtf_timing = "WAIT"
        if mtf_bias == "BULLISH" and mtf_setup != "NEUTRAL":
            if rsi_1m < 70 and macd_1m > -0.5: # not overbought, momentum not severely dumping
                mtf_timing = "CONFIRM_BUY"
        elif mtf_bias == "BEARISH" and mtf_setup != "NEUTRAL":
            if rsi_1m > 30 and macd_1m < 0.5:
                mtf_timing = "CONFIRM_SELL"
                
        # --- Resolution & Confluence ---
        recommendation = "WAIT"
        reasoning = []
        entry_min, entry_max = curr_price, curr_price
        stop_loss = None
        targets = []
        confidence = 0.0
        
        if mtf_bias == "BULLISH" and mtf_setup in ["PULLBACK_SUPPORT", "TREND_CONTINUATION"] and mtf_timing == "CONFIRM_BUY":
            recommendation = "BUY"
            reasoning.append(f"15m BIAS: Xu hướng chính đang TĂNG mạnh (Đồng thuận mtf_bias).")
            reasoning.append(f"5m SETUP: Cấu trúc {mtf_setup.replace('_', ' ')} thuận lợi cho vị thế Mua.")
            reasoning.append(f"1m TIMING: Xung lực ngắn hạn ủng hộ (RSI {rsi_1m:.1f}, MACD {macd_1m:.1f}).")
            
            if mtf_setup == "PULLBACK_SUPPORT" and imm_sup:
                entry_min, entry_max = imm_sup, curr_price
                stop_loss = imm_sup - (atr_5m * self.atr_buffer_mult)
            else:
                entry_min, entry_max = curr_price - (atr_5m * 0.5), curr_price
                stop_loss = ema21_5m - atr_5m
                
            if imm_res: targets.append(imm_res)
            if next_res and next_res != imm_res: targets.append(next_res)
            
            confidence = min(70 + (adx_1m * 0.5), 95)
            
        elif mtf_bias == "BEARISH" and mtf_setup in ["PULLBACK_RESISTANCE", "TREND_CONTINUATION"] and mtf_timing == "CONFIRM_SELL":
            recommendation = "SELL"
            reasoning.append(f"15m BIAS: Xu hướng chính đang GIẢM mạnh (Đồng thuận mtf_bias).")
            reasoning.append(f"5m SETUP: Cấu trúc {mtf_setup.replace('_', ' ')} thuận lợi cho vị thế Bán.")
            reasoning.append(f"1m TIMING: Xung lực ngắn hạn ủng hộ (RSI {rsi_1m:.1f}, MACD {macd_1m:.1f}).")
            
            if mtf_setup == "PULLBACK_RESISTANCE" and imm_res:
                entry_min, entry_max = curr_price, imm_res
                stop_loss = imm_res + (atr_5m * self.atr_buffer_mult)
            else:
                entry_min, entry_max = curr_price, curr_price + (atr_5m * 0.5)
                stop_loss = ema21_5m + atr_5m
                
            if imm_sup: targets.append(imm_sup)
            if next_sup and next_sup != imm_sup: targets.append(next_sup)
            
            confidence = min(70 + (adx_1m * 0.5), 95)
            
        else:
            if mtf_bias == "NEUTRAL":
                reasoning.append(f"15m BIAS: Thị trường đi ngang, chưa rõ xu hướng.")
                recommendation = "HOLD"
            else:
                reasoning.append(f"Xung đột đa khung thời gian: 15m {mtf_bias}, 5m {mtf_setup}, 1m {mtf_timing}.")
                reasoning.append("Tốt nhất nên đứng ngoài quan sát thêm.")
                recommendation = "WAIT"

        # Add Fib context to reasoning
        nearest_fib = fib_data_15m.get("nearest_level", "")
        if recommendation in ["BUY", "SELL"] and nearest_fib:
            reasoning.append(f"Vùng giá hiện tại đang sát mức Fibonacci {nearest_fib} (Khung 15m).")

        # Calculate Risk/Reward
        trailing_atr = None
        trailing_offset = None
        exit_strategy = ""
        if recommendation in ["BUY", "SELL"]:
            trailing_atr, trailing_offset = self._build_trailing_stop_plan(df_1m, curr_price)
            exit_strategy = "atr_trailing_stop_10m"

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
        if recommendation in ["BUY", "SELL"] and trailing_offset is not None:
            exit_note = f"Exit plan: trail stop by ATR {self.trailing_stop_atr_multiplier:.1f}x on 10m, offset ~{trailing_offset:,.1f}."
            if targets:
                exit_note += f" First profit map stays near {targets[0]:,.1f}."
            reasoning.append(exit_note)

        trend_short = "BULLISH" if mtf_bias == "BULLISH" else ("BEARISH" if mtf_bias == "BEARISH" else "NEUTRAL")
        momentum = "STRONG" if adx_1m >= 25 else ("MODERATE" if adx_1m >= 15 else "WEAK")

        rec = SignalRecommendation(
            symbol=symbol,
            timeframe="MTF(15m/5m/1m)",
            recommendation=recommendation,
            bias=mtf_bias,
            mtf_bias_15m=mtf_bias,
            mtf_setup_5m=mtf_setup,
            mtf_timing_1m=mtf_timing,
            confidence=round(confidence, 1),
            current_price=round(curr_price, 1),
            entry_zone=EntryZone(min_price=round(entry_min,1), max_price=round(entry_max,1)) if recommendation in ["BUY", "SELL"] else None,
            stop_loss=round(stop_loss, 1) if stop_loss else None,
            take_profit_targets=[round(t, 1) for t in targets],
            exit_strategy=exit_strategy,
            trailing_stop_timeframe="10m" if recommendation in ["BUY", "SELL"] else "",
            trailing_stop_atr_period=self.trailing_stop_atr_period,
            trailing_stop_atr_multiplier=self.trailing_stop_atr_multiplier if recommendation in ["BUY", "SELL"] else 0.0,
            trailing_stop_atr=trailing_atr,
            trailing_stop_offset=trailing_offset,
            supports=[round(s, 1) for s in supports],
            resistances=[round(r, 1) for r in resistances],
            nearest_fib_zone=nearest_fib,
            trend_short=trend_short,
            momentum=momentum,
            risk_reward_estimate=round(rr_ratio, 2),
            reasoning=reasoning,
            risk_note=(
                f"Protect with trailing ATR stop on 10m x{self.trailing_stop_atr_multiplier:.1f}; do not widen the stop once price moves in favor."
                if recommendation in ["BUY", "SELL"] else ""
            ),
            data_status="live",
            generated_at=datetime.now()
        )

        logger.info(f"SignalRecommenderEngine output: {rec.recommendation} | Confidence {rec.confidence}% | MTF: {mtf_bias}/{mtf_setup}/{mtf_timing}")
        return rec
