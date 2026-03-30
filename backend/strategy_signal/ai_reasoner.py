# backend/strategy_signal/ai_reasoner.py
# Ties the signal engine, database, and LLM together.

import pandas as pd
from loguru import logger
from typing import Dict, Any, Optional
from datetime import datetime

from agent.llm_client import AIClient
from agent.prompt import SYSTEM_PROMPT, build_trading_prompt, INSIGHT_SYSTEM_PROMPT, build_insight_prompt
from agent.strategies.orb import OpeningRangeBreakoutStrategy
from agent.strategies.base import StrategyConfig
from shared.models import TradeIntent
from shared.enums import TradeAction, OrderType

class AIReasoningService:
    """
    Manages the lifecycle of an AI-driven trading decision.
    Receives indicator signals -> Pulls recent market data -> Consults LLM -> Emits standardized TradeIntent.
    """
    def __init__(self):
        self.llm = AIClient()
        self.strategies = [
            OpeningRangeBreakoutStrategy(StrategyConfig(name="orb"))
        ]
        
    async def process_signal(self, pre_signal: dict, df: pd.DataFrame, active_positions_count: int = 0) -> Optional[TradeIntent]:
        """
        Takes the deterministic signal and passes it to the AI for final evaluation.
        Returns a TradeIntent if approved, else None.
        """
        symbol = pre_signal.get("symbol", "UNKNOWN")
        logger.info(f"AIReasoningService evaluating signal for {symbol}: {pre_signal['action']} (Conf: {pre_signal['confidence']})")
        
        # 1. Check if we already have an active position
        if active_positions_count > 0:
            logger.debug(f"Skipping AI analysis: {active_positions_count} active position(s) exist.")
            return None
            
        # 1.5 Check if market is open
        from data.realtime_feed import is_vn_market_open
        if not is_vn_market_open():
            logger.info(f"Market Closed: Overriding {symbol} signal to WAIT (Action: HOLD)")
            return TradeIntent(
                strategy_name="AI_Orchestrator_v1",
                symbol=symbol,
                action=TradeAction.HOLD,
                confidence=100.0,
                entry_type=OrderType.MARKET,
                entry_price=None,
                qty=0,
                stop_loss=None,
                take_profit=None,
                reason="Market is currently closed. Evaluating based on last closing price. Action forced to WAIT.",
                timeframe="1m",
                metadata={"action": "HOLD", "rationale": "Market is currently closed."}
            )
            
        # 2. Run Deterministic Strategies for Confluence
        strategy_signals = []
        market_state = {"df": df, "symbol": symbol}
        
        for strategy in self.strategies:
            sig = await strategy.generate_signal(market_state)
            if sig:
                strategy_signals.append(sig)
                logger.info(f"Strategy {strategy.name} generated confluence signal: {sig['action']}")

        # 3. Build Prompt Context
        try:
            # Slice last 5 candles for temporal context
            history_df = df.tail(5)
            recent_candles = history_df.reset_index().to_dict(orient="records")
            
            # Liquidity Check (Safety Gate)
            avg_volume = df["volume"].tail(20).mean()
            current_volume = df["volume"].iloc[-1]
            if current_volume < (avg_volume * 0.2):
                logger.warning(f"Liquidity Check FAILED: Volume {current_volume} is too low (Avg: {avg_volume:.0f})")
                return None
                
            # Add strategy signals to prompt if available
            if strategy_signals:
                pre_signal["strategy_confluence"] = strategy_signals
                
            user_prompt = build_trading_prompt(pre_signal, recent_candles)
        except Exception as e:
            logger.error(f"Failed to build AI prompt: {e}")
            return None
            
        # 4. Call LLM
        logger.debug("Consulting AI Agent...")
        decision_dict = await self.llm.analyze_market(SYSTEM_PROMPT, user_prompt)
        
        if not decision_dict:
            logger.warning("AI Agent returned no actionable decision.")
            return None
            
        # 5. Validate AI Decision
        action_str = decision_dict.get("action", "HOLD").upper()
        confidence = decision_dict.get("confidence", 0)
        
        if action_str not in ["LONG", "SHORT"]:
            logger.info(f"AI decided to HOLD/WAIT (Action: {action_str})")
            return None

        if confidence < 80:
            logger.warning(f"Trade REJECTED: AI Confidence {confidence}% < 80% threshold.")
            return None
            
        entry = decision_dict.get("entry", 0)
        stop_loss = decision_dict.get("stop_loss", 0)
        tps = decision_dict.get("take_profit", [])
        
        # Risk Check (R:R Ratio)
        if entry and stop_loss and tps:
            risk = abs(entry - stop_loss)
            reward = abs(tps[0] - entry)
            if risk > 0 and (reward / risk) < 1.5:
                logger.warning(f"Trade REJECTED: R:R ratio {(reward/risk):.2f} < 1.5 benchmark.")
                return None

        # Map internal AI naming (LONG/SHORT) to TradeAction
        trade_action = TradeAction.BUY if action_str == "LONG" else TradeAction.SELL

        # 6. Construct TradeIntent
        intent = TradeIntent(
            strategy_name="AI_Orchestrator_v1",
            symbol=symbol,
            action=trade_action,
            confidence=float(confidence),
            entry_type=OrderType.MARKET,
            entry_price=float(entry) if entry else None,
            qty=0, # qty to be determined by Risk Engine / Execution Layer
            stop_loss=float(stop_loss) if stop_loss else None,
            take_profit=[float(tp) for tp in tps] if isinstance(tps, list) else None,
            reason=decision_dict.get("rationale", "AI confirmed signal"),
            timeframe="1m",
            ai_source=self.llm.provider.upper(),
            metadata=decision_dict
        )
        
        logger.success(f"[STRATEGY SIGNAL]: Approved {intent.action} for {intent.symbol} - {intent.reason}")
        return intent

    async def generate_market_insight(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Periodically fetches market context to generate a rich structured dashboard insight.
        Computes S/R, Fibonacci, and full indicator context, then queries LLM.
        Returns a dict compatible with MarketSummary for WebSocket broadcast.
        
        Data quality aware: validates indicators instead of using misleading fallbacks.
        """
        try:
            from indicators.engine import build_features, calculate_support_resistance, calculate_fibonacci, validate_technical_data
            from shared.models import MarketSummary, FibonacciLevel
            import math
            
            bars_count = len(df)
            logger.info(f"AI Insight: Processing {bars_count} bars for market insight")
            
            features_df = build_features(df)
            if features_df is None or features_df.empty:
                return None

            # --- 0. Validate data quality ---
            quality_report = validate_technical_data(features_df)
            data_quality = quality_report["data_quality"]
            missing_indicators = quality_report["missing_indicators"]
            
            if missing_indicators:
                logger.warning(f"AI Insight data quality: {data_quality} | Missing: {missing_indicators} | Bars: {bars_count}")
            else:
                logger.info(f"AI Insight data quality: FULL | Bars: {bars_count}")

            # --- 1. Compute quantitative context from real data ---
            last = features_df.iloc[-1]
            first = features_df.iloc[0]
            
            current_price = float(last["close"])
            open_price = float(first["open"])
            period_high = float(features_df["high"].max())
            period_low = float(features_df["low"].min())
            price_change = round(current_price - open_price, 1)
            price_change_pct = round((price_change / open_price * 100) if open_price else 0, 2)

            # Helper: safe read — returns None if NaN or missing instead of fallback
            def safe_float(series_val, default=None):
                if series_val is None:
                    return default
                try:
                    v = float(series_val)
                    return default if (math.isnan(v) or math.isinf(v)) else v
                except (ValueError, TypeError):
                    return default

            ema9 = safe_float(last.get("ema_9"), None)
            ema21 = safe_float(last.get("ema_21"), None)
            rsi = safe_float(last.get("rsi_14"), None)
            macd_hist = safe_float(last.get("macd_hist"), None)
            adx = safe_float(last.get("adx_14"), None)
            atr = safe_float(last.get("atr_14"), None)
            bb_upper = safe_float(last.get("bb_upper"), None)
            bb_lower = safe_float(last.get("bb_lower"), None)
            vwap = safe_float(last.get("vwap"), None)
            st_dir_raw = safe_float(last.get("supertrend_dir"), None)
            st_dir = int(st_dir_raw) if st_dir_raw is not None else 0

            # Volume ratio: current vs 20-bar average
            avg_vol = float(features_df["volume"].tail(20).mean())
            current_vol = float(last["volume"])
            vol_ratio = round(current_vol / avg_vol, 2) if avg_vol > 0 else 1.0

            # EMA position (only if EMA values exist)
            if ema9 is not None:
                price_vs_ema9 = "ABOVE" if current_price > ema9 else ("BELOW" if current_price < ema9 else "AT")
            else:
                price_vs_ema9 = "AT"
            if ema21 is not None:
                price_vs_ema21 = "ABOVE" if current_price > ema21 else ("BELOW" if current_price < ema21 else "AT")
            else:
                price_vs_ema21 = "AT"

            # --- 2. Calculate S/R and Fibonacci from real price structure ---
            sr_levels = calculate_support_resistance(features_df, lookback=20)
            fib_data = calculate_fibonacci(features_df, lookback=30)
            
            # Track S/R and Fib insufficiency
            if not sr_levels.get("supports") and not sr_levels.get("resistances"):
                if "support_resistance" not in missing_indicators:
                    missing_indicators.append("support_resistance")
            if not fib_data or not fib_data.get("levels"):
                if "fibonacci" not in missing_indicators:
                    missing_indicators.append("fibonacci")

            # Recalculate quality based on final missing list
            if not missing_indicators:
                data_quality = "full"
            elif len(missing_indicators) <= 3:
                data_quality = "partial"
            else:
                data_quality = "price_action_only"

            fib_levels = []
            if fib_data and fib_data.get("levels"):
                for fl in fib_data["levels"]:
                    if fl["level"] in [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]:
                        fib_levels.append(FibonacciLevel(level=fl["level"], price=fl["price"]))

            # --- 3. Build rich prompt with all context ---
            history_df = features_df.tail(20)
            recent_candles = history_df.reset_index().to_dict(orient="records")
            
            user_prompt = build_insight_prompt(
                recent_candles=recent_candles,
                sr_levels=sr_levels,
                fib_data=fib_data
            )
            
            # Append data quality warning to prompt so LLM knows
            if data_quality != "full":
                user_prompt += f"\n\n[DATA QUALITY WARNING]\nChất lượng dữ liệu: {data_quality.upper()}\nChỉ báo thiếu: {', '.join(missing_indicators)}\nSố nến: {bars_count}\nHãy lưu ý trong phân tích: chỉ dùng dữ liệu có sẵn, nếu thiếu hãy ghi rõ trong risk_note."

            from data.realtime_feed import is_vn_market_open
            if not is_vn_market_open():
                logger.debug("Market is closed. Skipping LLM insight generation.")
                ai_dict = {
                    "regime": "CLOSED",
                    "bias": "NEUTRAL",
                    "one_liner": "Thị trường đang đóng cửa. Dữ liệu dựa trên giá đóng cửa phiên trước.",
                    "trend_short": "NEUTRAL",
                    "trend_medium": "NEUTRAL",
                    "momentum": "FLAT",
                    "scenario_bullish": "Chờ phiên giao dịch tiếp theo.",
                    "scenario_bearish": "Chờ phiên giao dịch tiếp theo.",
                    "risk_note": "Thị trường nghỉ giao dịch.",
                    "confidence": 0,
                }
            else:
                logger.debug("Generating rich market AI insight...")
                ai_dict = await self.llm.analyze_market(INSIGHT_SYSTEM_PROMPT, user_prompt)

                if not ai_dict:
                    return None

            # --- 4. Assemble full MarketSummary combining real calcs + LLM narrative ---
            summary = MarketSummary(
                # Price context (from real data)
                current_price=current_price,
                price_change=price_change,
                price_change_pct=price_change_pct,
                period_high=period_high,
                period_low=period_low,

                # Indicators (from real data — use 0.0 only when truly None for JSON compat)
                rsi=round(rsi, 1) if rsi is not None else 0.0,
                macd_hist=round(macd_hist, 4) if macd_hist is not None else 0.0,
                adx=round(adx, 1) if adx is not None else 0.0,
                atr=round(atr, 2) if atr is not None else 0.0,
                volume_ratio=vol_ratio,
                ema9=round(ema9, 1) if ema9 is not None else 0.0,
                ema21=round(ema21, 1) if ema21 is not None else 0.0,
                price_vs_ema9=price_vs_ema9,
                price_vs_ema21=price_vs_ema21,
                supertrend_dir=st_dir,

                # S/R (from real data)
                supports=sr_levels.get("supports", []),
                resistances=sr_levels.get("resistances", []),

                # Fibonacci (from real data)
                swing_high=fib_data.get("swing_high", 0.0) if fib_data else 0.0,
                swing_low=fib_data.get("swing_low", 0.0) if fib_data else 0.0,
                fibonacci_levels=fib_levels,
                nearest_fib_zone=fib_data.get("nearest_level", "") if fib_data else "",

                # AI narrative (from LLM)
                regime=ai_dict.get("regime", "CHOPPY"),
                bias=ai_dict.get("bias", "NEUTRAL"),
                one_liner=ai_dict.get("one_liner", ""),
                trend_short=ai_dict.get("trend_short", "NEUTRAL"),
                trend_medium=ai_dict.get("trend_medium", "NEUTRAL"),
                momentum=ai_dict.get("momentum", "WEAK"),
                scenario_bullish=ai_dict.get("scenario_bullish", ""),
                scenario_bearish=ai_dict.get("scenario_bearish", ""),
                risk_note=ai_dict.get("risk_note", ""),
                confidence=int(ai_dict.get("confidence", 50)),
                ai_source=self.llm.provider.upper(),
                
                # Data quality metadata
                data_quality=data_quality,
                missing_indicators=missing_indicators,
                bars_used=bars_count,
            )

            return summary.model_dump(mode="json")

        except Exception as e:
            logger.error(f"Failed to generate AI insight: {e}")
            import traceback
            traceback.print_exc()
            return None

