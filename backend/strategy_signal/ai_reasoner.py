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
            metadata=decision_dict
        )
        
        logger.success(f"[STRATEGY SIGNAL]: Approved {intent.action} for {intent.symbol} - {intent.reason}")
        return intent

    async def generate_market_insight(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Periodically fetches market context to generate a rich structured dashboard insight.
        Computes S/R, Fibonacci, and full indicator context, then queries LLM.
        Returns a dict compatible with MarketSummary for WebSocket broadcast.
        """
        try:
            from indicators.engine import build_features, calculate_support_resistance, calculate_fibonacci
            from shared.models import MarketSummary, FibonacciLevel
            
            features_df = build_features(df)
            if features_df is None or features_df.empty:
                return None

            # --- 1. Compute quantitative context from real data ---
            last = features_df.iloc[-1]
            first = features_df.iloc[0]
            
            current_price = float(last["close"])
            open_price = float(first["open"])
            period_high = float(features_df["high"].max())
            period_low = float(features_df["low"].min())
            price_change = round(current_price - open_price, 1)
            price_change_pct = round((price_change / open_price * 100) if open_price else 0, 2)

            ema9 = float(last.get("ema_9", 0))
            ema21 = float(last.get("ema_21", 0))
            rsi = float(last.get("rsi_14", 50))
            macd_hist = float(last.get("macd_hist", 0))
            adx = float(last.get("adx_14", 0))
            atr = float(last.get("atr_14", 0))
            st_dir = int(last.get("supertrend_dir", 0))

            # Volume ratio: current vs 20-bar average
            avg_vol = float(features_df["volume"].tail(20).mean())
            current_vol = float(last["volume"])
            vol_ratio = round(current_vol / avg_vol, 2) if avg_vol > 0 else 1.0

            # EMA position
            price_vs_ema9 = "ABOVE" if current_price > ema9 else ("BELOW" if current_price < ema9 else "AT")
            price_vs_ema21 = "ABOVE" if current_price > ema21 else ("BELOW" if current_price < ema21 else "AT")

            # --- 2. Calculate S/R and Fibonacci from real price structure ---
            sr_levels = calculate_support_resistance(features_df, lookback=20)
            fib_data = calculate_fibonacci(features_df, lookback=30)

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

                # Indicators (from real data)
                rsi=rsi,
                macd_hist=round(macd_hist, 4),
                adx=round(adx, 1),
                atr=round(atr, 2),
                volume_ratio=vol_ratio,
                ema9=round(ema9, 1),
                ema21=round(ema21, 1),
                price_vs_ema9=price_vs_ema9,
                price_vs_ema21=price_vs_ema21,
                supertrend_dir=st_dir,

                # S/R (from real data)
                supports=sr_levels.get("supports", []),
                resistances=sr_levels.get("resistances", []),

                # Fibonacci (from real data)
                swing_high=fib_data.get("swing_high", 0.0),
                swing_low=fib_data.get("swing_low", 0.0),
                fibonacci_levels=fib_levels,
                nearest_fib_zone=fib_data.get("nearest_level", ""),

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
            )

            return summary.model_dump(mode="json")

        except Exception as e:
            logger.error(f"Failed to generate AI insight: {e}")
            return None

