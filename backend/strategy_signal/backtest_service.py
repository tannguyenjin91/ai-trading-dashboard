from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from shared.models import SignalRecommendation
from indicators.engine import calculate_atr
from strategy_signal.recommender import SignalRecommenderEngine
from strategy_signal.strategy_settings import StrategySettings


@dataclass
class OpenTrade:
    direction: str
    entry_time: datetime
    entry_price: float
    quantity: int
    stop_loss: float | None
    take_profit: float | None
    signal_id: str
    confidence: float
    exit_strategy: str
    trailing_stop: float | None
    trailing_offset: float | None
    trailing_atr: float | None
    trailing_stop_timeframe: str
    trail_high: float
    trail_low: float


class BacktestService:
    SUPPORTED_STRATEGIES = ("mtf_signal", "ema_cross", "breakout_retest")

    def __init__(self, recommender: SignalRecommenderEngine):
        self.recommender = recommender

    def run(
        self,
        symbol: str,
        df_1m: pd.DataFrame,
        settings: StrategySettings,
        min_confidence: float | None = None,
        strategy_name: str = "mtf_signal",
    ) -> dict[str, Any]:
        if df_1m.empty or len(df_1m) < 220:
            return {"error": "Not enough data to backtest. Need at least 220 one-minute bars."}
        if strategy_name not in self.SUPPORTED_STRATEGIES:
            return {"error": f"Unsupported strategy '{strategy_name}'."}

        threshold = float(min_confidence if min_confidence is not None else settings.min_confidence)
        capital = float(settings.initial_capital)
        base_capital = capital
        trade: OpenTrade | None = None
        trades: list[dict[str, Any]] = []
        equity_curve: list[dict[str, Any]] = []

        df_1m = df_1m.sort_index().copy()
        evaluation_indexes = range(180, len(df_1m), 5)

        for i in evaluation_indexes:
            window_1m = df_1m.iloc[: i + 1]
            current_bar = window_1m.iloc[-1]
            current_time = window_1m.index[-1]
            current_price = float(current_bar["close"])
            df_5m = self._resample(window_1m, "5min")
            df_10m = self._resample(window_1m, "10min")
            df_15m = self._resample(window_1m, "15min")

            if trade is not None:
                self._update_trailing_stop(trade, current_bar, self._latest_atr(df_10m))
                exit_info = self._check_exit(trade, current_bar, current_time)
                if exit_info is not None:
                    pnl = self._pnl(trade.direction, trade.entry_price, exit_info["exit_price"], trade.quantity)
                    capital += pnl
                    trades.append(
                        {
                            "signal_id": trade.signal_id,
                            "symbol": symbol,
                            "direction": trade.direction,
                            "entry_time": trade.entry_time.isoformat(),
                            "exit_time": current_time.isoformat(),
                            "entry_price": trade.entry_price,
                            "exit_price": exit_info["exit_price"],
                            "quantity": trade.quantity,
                            "pnl": pnl,
                            "return_pct": (pnl / max(base_capital, 1)) * 100,
                            "close_reason": exit_info["reason"],
                            "confidence": trade.confidence,
                        }
                    )
                    trade = None

            if len(df_5m) < 50 or len(df_15m) < 20:
                equity_curve.append({"time": current_time.isoformat(), "equity": capital})
                continue

            recommendation = self._generate_strategy_signal(
                strategy_name=strategy_name,
                symbol=symbol,
                df_1m=window_1m,
                df_5m=df_5m,
                df_10m=df_10m,
                df_15m=df_15m,
            )

            if trade is not None and recommendation and recommendation.recommendation in {"BUY", "SELL"}:
                if recommendation.recommendation != trade.direction and recommendation.confidence >= threshold:
                    pnl = self._pnl(trade.direction, trade.entry_price, current_price, trade.quantity)
                    capital += pnl
                    trades.append(
                        {
                            "signal_id": trade.signal_id,
                            "symbol": symbol,
                            "direction": trade.direction,
                            "entry_time": trade.entry_time.isoformat(),
                            "exit_time": current_time.isoformat(),
                            "entry_price": trade.entry_price,
                            "exit_price": current_price,
                            "quantity": trade.quantity,
                            "pnl": pnl,
                            "return_pct": (pnl / max(base_capital, 1)) * 100,
                            "close_reason": "signal_flip",
                            "confidence": trade.confidence,
                        }
                    )
                    trade = None

            if trade is None and self._should_open_trade(recommendation, threshold, settings):
                trade = self._open_trade(recommendation, settings, capital, current_time)

            mark_to_market = capital
            if trade is not None:
                mark_to_market += self._pnl(trade.direction, trade.entry_price, current_price, trade.quantity)
            equity_curve.append({"time": current_time.isoformat(), "equity": round(mark_to_market, 2)})

        if trade is not None:
            final_price = float(df_1m.iloc[-1]["close"])
            final_time = df_1m.index[-1]
            pnl = self._pnl(trade.direction, trade.entry_price, final_price, trade.quantity)
            capital += pnl
            trades.append(
                {
                    "signal_id": trade.signal_id,
                    "symbol": symbol,
                    "direction": trade.direction,
                    "entry_time": trade.entry_time.isoformat(),
                    "exit_time": final_time.isoformat(),
                    "entry_price": trade.entry_price,
                    "exit_price": final_price,
                    "quantity": trade.quantity,
                    "pnl": pnl,
                    "return_pct": (pnl / max(base_capital, 1)) * 100,
                    "close_reason": "end_of_test",
                    "confidence": trade.confidence,
                }
            )

        metrics = self._build_metrics(base_capital, capital, trades, equity_curve)
        logger.info(f"Backtest completed for {symbol}: {metrics['total_trades']} trades")
        return {
            "symbol": symbol,
            "strategy": strategy_name,
            "interval": "1m/5m/15m",
            "started_at": df_1m.index[0].isoformat(),
            "ended_at": df_1m.index[-1].isoformat(),
            "metrics": metrics,
            "equity_curve": equity_curve[-300:],
            "trades": trades[-100:],
        }

    @staticmethod
    def _resample(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        resampled = (
            df.resample(timeframe)
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna()
        )
        return resampled

    def _generate_strategy_signal(
        self,
        strategy_name: str,
        symbol: str,
        df_1m: pd.DataFrame,
        df_5m: pd.DataFrame,
        df_10m: pd.DataFrame,
        df_15m: pd.DataFrame,
    ) -> SignalRecommendation | None:
        if strategy_name == "mtf_signal":
            return self.recommender.generate_recommendation(df_1m, df_5m, df_15m, symbol)
        if strategy_name == "ema_cross":
            return self._ema_cross_signal(symbol, df_1m, df_10m, df_15m)
        if strategy_name == "breakout_retest":
            return self._breakout_retest_signal(symbol, df_1m, df_10m, df_15m)
        return None

    @staticmethod
    def _ema_cross_signal(symbol: str, df_1m: pd.DataFrame, df_10m: pd.DataFrame, df_15m: pd.DataFrame) -> SignalRecommendation | None:
        if len(df_15m) < 40:
            return None
        fast = df_15m["close"].ewm(span=9).mean()
        slow = df_15m["close"].ewm(span=21).mean()
        if len(fast) < 2 or len(slow) < 2:
            return None

        prev_fast, curr_fast = float(fast.iloc[-2]), float(fast.iloc[-1])
        prev_slow, curr_slow = float(slow.iloc[-2]), float(slow.iloc[-1])
        current_price = float(df_1m["close"].iloc[-1])
        atr = float((df_15m["high"] - df_15m["low"]).rolling(14).mean().iloc[-1] or 0)
        trailing_atr = BacktestService._latest_atr(df_10m) or current_price * 0.0035
        trailing_offset = max(trailing_atr * 2.0, current_price * 0.003)
        stop_buffer = atr if atr > 0 else current_price * 0.006

        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return SignalRecommendation(
                symbol=symbol,
                recommendation="BUY",
                bias="BULLISH",
                confidence=68.0,
                current_price=current_price,
                entry_zone={"min_price": current_price * 0.998, "max_price": current_price * 1.002},
                stop_loss=current_price - stop_buffer,
                take_profit_targets=[current_price + stop_buffer * 2],
                exit_strategy="atr_trailing_stop_10m",
                trailing_stop_timeframe="10m",
                trailing_stop_atr_period=14,
                trailing_stop_atr_multiplier=2.0,
                trailing_stop_atr=round(trailing_atr, 1),
                trailing_stop_offset=round(trailing_offset, 1),
                trend_short="EMA_CROSS_UP",
                trend_medium="BULLISH",
                momentum="MODERATE",
                reasoning=["EMA 9 has crossed above EMA 21 on the 15m structure."],
                risk_note="Exit with ATR trailing stop on 10m x2.0; do not widen the stop if price rolls over.",
                risk_reward_estimate=2.0,
            )
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return SignalRecommendation(
                symbol=symbol,
                recommendation="SELL",
                bias="BEARISH",
                confidence=68.0,
                current_price=current_price,
                entry_zone={"min_price": current_price * 0.998, "max_price": current_price * 1.002},
                stop_loss=current_price + stop_buffer,
                take_profit_targets=[current_price - stop_buffer * 2],
                exit_strategy="atr_trailing_stop_10m",
                trailing_stop_timeframe="10m",
                trailing_stop_atr_period=14,
                trailing_stop_atr_multiplier=2.0,
                trailing_stop_atr=round(trailing_atr, 1),
                trailing_stop_offset=round(trailing_offset, 1),
                trend_short="EMA_CROSS_DOWN",
                trend_medium="BEARISH",
                momentum="MODERATE",
                reasoning=["EMA 9 has crossed below EMA 21 on the 15m structure."],
                risk_note="Exit with ATR trailing stop on 10m x2.0; cover quickly if price squeezes back above structure.",
                risk_reward_estimate=2.0,
            )
        return None

    @staticmethod
    def _breakout_retest_signal(symbol: str, df_1m: pd.DataFrame, df_10m: pd.DataFrame, df_15m: pd.DataFrame) -> SignalRecommendation | None:
        if len(df_15m) < 30 or len(df_1m) < 50:
            return None
        recent = df_15m.tail(20)
        range_high = float(recent["high"].max())
        range_low = float(recent["low"].min())
        current_price = float(df_1m["close"].iloc[-1])
        previous_price = float(df_1m["close"].iloc[-5])
        buffer = max((range_high - range_low) * 0.18, current_price * 0.005)
        trailing_atr = BacktestService._latest_atr(df_10m) or current_price * 0.0035
        trailing_offset = max(trailing_atr * 2.0, current_price * 0.003)

        if current_price > range_high and previous_price <= range_high:
            return SignalRecommendation(
                symbol=symbol,
                recommendation="BUY",
                bias="BULLISH",
                confidence=72.0,
                current_price=current_price,
                entry_zone={"min_price": range_high, "max_price": current_price},
                stop_loss=range_high - buffer,
                take_profit_targets=[current_price + buffer * 2.2],
                exit_strategy="atr_trailing_stop_10m",
                trailing_stop_timeframe="10m",
                trailing_stop_atr_period=14,
                trailing_stop_atr_multiplier=2.0,
                trailing_stop_atr=round(trailing_atr, 1),
                trailing_stop_offset=round(trailing_offset, 1),
                supports=[range_high],
                resistances=[range_high + buffer * 2.2],
                trend_short="BREAKOUT",
                trend_medium="BULLISH",
                momentum="STRONG",
                reasoning=["Price has broken above the 20-bar 15m range with fresh momentum."],
                risk_note="Trail the stop by ATR 10m x2.0 after entry; do not let a breakout retrace below the trailed floor.",
                risk_reward_estimate=2.2,
            )
        if current_price < range_low and previous_price >= range_low:
            return SignalRecommendation(
                symbol=symbol,
                recommendation="SELL",
                bias="BEARISH",
                confidence=72.0,
                current_price=current_price,
                entry_zone={"min_price": current_price, "max_price": range_low},
                stop_loss=range_low + buffer,
                take_profit_targets=[current_price - buffer * 2.2],
                exit_strategy="atr_trailing_stop_10m",
                trailing_stop_timeframe="10m",
                trailing_stop_atr_period=14,
                trailing_stop_atr_multiplier=2.0,
                trailing_stop_atr=round(trailing_atr, 1),
                trailing_stop_offset=round(trailing_offset, 1),
                supports=[range_low - buffer * 2.2],
                resistances=[range_low],
                trend_short="BREAKDOWN",
                trend_medium="BEARISH",
                momentum="STRONG",
                reasoning=["Price has broken below the 20-bar 15m range with downside follow-through."],
                risk_note="Trail the stop by ATR 10m x2.0 after entry; if price reclaims the range, close the short.",
                risk_reward_estimate=2.2,
            )
        return None

    @staticmethod
    def _should_open_trade(
        recommendation: SignalRecommendation | None,
        threshold: float,
        settings: StrategySettings,
    ) -> bool:
        if recommendation is None:
            return False
        if recommendation.recommendation not in {"BUY", "SELL"}:
            return False
        if recommendation.recommendation == "SELL" and not settings.allow_short:
            return False
        if recommendation.confidence < threshold:
            return False
        if recommendation.stop_loss is None:
            return False
        return True

    @staticmethod
    def _open_trade(
        recommendation: SignalRecommendation,
        settings: StrategySettings,
        capital: float,
        entry_time: datetime,
    ) -> OpenTrade:
        entry_price = float(recommendation.current_price)
        stop_loss = recommendation.stop_loss
        take_profit = recommendation.take_profit_targets[0] if recommendation.take_profit_targets else None
        risk_per_unit = abs(entry_price - (stop_loss or entry_price * 0.995))
        capital_at_risk = capital * max(settings.risk_per_trade_pct, 0.1) / 100
        quantity = max(1, math.floor(capital_at_risk / max(risk_per_unit, entry_price * 0.0025)))
        trailing_stop = recommendation.stop_loss
        return OpenTrade(
            direction=recommendation.recommendation,
            entry_time=entry_time,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal_id=recommendation.signal_id,
            confidence=float(recommendation.confidence),
            exit_strategy=recommendation.exit_strategy or "fixed_sl_tp",
            trailing_stop=trailing_stop,
            trailing_offset=recommendation.trailing_stop_offset,
            trailing_atr=recommendation.trailing_stop_atr,
            trailing_stop_timeframe=recommendation.trailing_stop_timeframe or "10m",
            trail_high=entry_price,
            trail_low=entry_price,
        )

    @staticmethod
    def _latest_atr(df: pd.DataFrame, period: int = 14) -> float | None:
        if df.empty or len(df) < period:
            return None
        atr_series = calculate_atr(df, period).dropna()
        if atr_series.empty:
            return None
        return float(atr_series.iloc[-1])

    @staticmethod
    def _update_trailing_stop(trade: OpenTrade, bar: pd.Series, atr_value: float | None) -> None:
        trailing_offset = trade.trailing_offset
        if (trailing_offset is None or trailing_offset <= 0) and atr_value and atr_value > 0:
            trailing_offset = max(atr_value * 2.0, trade.entry_price * 0.003)
            trade.trailing_offset = trailing_offset
            trade.trailing_atr = atr_value
        if trailing_offset is None or trailing_offset <= 0:
            return

        high = float(bar["high"])
        low = float(bar["low"])
        if trade.direction == "BUY":
            trade.trail_high = max(trade.trail_high, high)
            candidate_stop = trade.trail_high - trailing_offset
            trade.trailing_stop = candidate_stop if trade.trailing_stop is None else max(trade.trailing_stop, candidate_stop)
        else:
            trade.trail_low = min(trade.trail_low, low)
            candidate_stop = trade.trail_low + trailing_offset
            trade.trailing_stop = candidate_stop if trade.trailing_stop is None else min(trade.trailing_stop, candidate_stop)

        if trade.trailing_stop is not None:
            if trade.stop_loss is None:
                trade.stop_loss = trade.trailing_stop
            elif trade.direction == "BUY":
                trade.stop_loss = max(trade.stop_loss, trade.trailing_stop)
            else:
                trade.stop_loss = min(trade.stop_loss, trade.trailing_stop)

    @staticmethod
    def _check_exit(
        trade: OpenTrade,
        bar: pd.Series,
        current_time: datetime,
    ) -> dict[str, Any] | None:
        high = float(bar["high"])
        low = float(bar["low"])
        stop_reason = "atr_trailing_stop" if trade.exit_strategy.startswith("atr_trailing_stop") else "stop_loss"
        if trade.direction == "BUY":
            if trade.stop_loss is not None and low <= trade.stop_loss:
                return {"exit_price": float(trade.stop_loss), "time": current_time, "reason": stop_reason}
            if trade.take_profit is not None and high >= trade.take_profit:
                return {"exit_price": float(trade.take_profit), "time": current_time, "reason": "take_profit"}
        else:
            if trade.stop_loss is not None and high >= trade.stop_loss:
                return {"exit_price": float(trade.stop_loss), "time": current_time, "reason": stop_reason}
            if trade.take_profit is not None and low <= trade.take_profit:
                return {"exit_price": float(trade.take_profit), "time": current_time, "reason": "take_profit"}
        return None

    @staticmethod
    def _pnl(direction: str, entry_price: float, exit_price: float, quantity: int) -> float:
        multiplier = 1 if direction == "BUY" else -1
        return (exit_price - entry_price) * quantity * multiplier

    @staticmethod
    def _build_metrics(
        starting_capital: float,
        ending_capital: float,
        trades: list[dict[str, Any]],
        equity_curve: list[dict[str, Any]],
    ) -> dict[str, Any]:
        realized = ending_capital - starting_capital
        wins = [trade for trade in trades if trade["pnl"] > 0]
        losses = [trade for trade in trades if trade["pnl"] < 0]
        gross_profit = sum(trade["pnl"] for trade in wins)
        gross_loss = abs(sum(trade["pnl"] for trade in losses))
        win_rate = (len(wins) / len(trades) * 100) if trades else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float(gross_profit > 0)

        equity_values = np.array([point["equity"] for point in equity_curve], dtype=float)
        if len(equity_values) > 1:
            running_max = np.maximum.accumulate(equity_values)
            drawdowns = (equity_values - running_max) / np.maximum(running_max, 1)
            max_drawdown = float(drawdowns.min() * 100)
            returns = np.diff(equity_values) / np.maximum(equity_values[:-1], 1)
            sharpe = float((returns.mean() / returns.std()) * math.sqrt(len(returns))) if returns.std() > 0 else 0.0
        else:
            max_drawdown = 0.0
            sharpe = 0.0

        return {
            "starting_capital": starting_capital,
            "ending_capital": ending_capital,
            "net_profit": realized,
            "total_return_pct": (realized / max(starting_capital, 1)) * 100,
            "total_trades": len(trades),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown_pct": max_drawdown,
            "sharpe": sharpe,
            "avg_trade_pnl": (realized / len(trades)) if trades else 0.0,
        }
