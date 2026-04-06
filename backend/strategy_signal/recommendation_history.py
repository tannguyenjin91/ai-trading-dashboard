from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import aiosqlite
import pandas as pd
from loguru import logger

from agent.prompt import RECOMMENDATION_SYSTEM_PROMPT, build_recommendation_prompt
from indicators.engine import build_features
from shared.models import SignalRecommendation
from strategy_signal.recommender import SignalRecommenderEngine
from strategy_signal.strategy_settings import StrategySettings


class RecommendationHistoryService:
    def __init__(self, db_path: str = "market_data.db"):
        self.db_path = db_path

    async def init_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS recommendation_replay_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    include_ai INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL,
                    total_signals INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS recommendation_replay_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    replay_index INTEGER NOT NULL,
                    signal_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    generated_at TEXT NOT NULL,
                    current_price REAL NOT NULL,
                    ai_applied INTEGER NOT NULL DEFAULT 0,
                    app_payload TEXT NOT NULL,
                    ai_payload TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES recommendation_replay_runs(id)
                )
                """
            )
            await db.execute(
                """
                UPDATE recommendation_replay_runs
                SET status = 'interrupted', completed_at = ?
                WHERE status = 'running'
                """,
                (datetime.utcnow().isoformat(),),
            )
            await db.commit()

    async def create_run(
        self,
        symbol: str,
        provider: str,
        start_date: str,
        end_date: str,
        include_ai: bool,
    ) -> int:
        return await self._create_run(symbol, provider, start_date, end_date, include_ai)

    async def has_running_run(self, symbol: str | None = None) -> dict[str, Any] | None:
        query = [
            "SELECT * FROM recommendation_replay_runs",
            "WHERE status = 'running'",
        ]
        params: list[Any] = []
        if symbol:
            query.append("AND symbol = ?")
            params.append(symbol)
        query.append("ORDER BY created_at DESC, id DESC LIMIT 1")

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("\n".join(query), tuple(params)) as cursor:
                row = await cursor.fetchone()
        return self._serialize_run(row) if row else None

    async def execute_replay(
        self,
        run_id: int,
        symbol: str,
        provider: str,
        start_date: str,
        end_date: str,
        settings: StrategySettings,
        recommender: SignalRecommenderEngine,
        ai_service,
        df_1m: pd.DataFrame,
        include_ai: bool = True,
    ) -> dict[str, Any]:
        total_signals = 0
        stored_items: list[dict[str, Any]] = []
        last_signature: tuple[Any, ...] | None = None
        active_position: dict[str, Any] | None = None

        try:
            df_1m = df_1m.sort_index().copy()
            for replay_index in range(180, len(df_1m), 5):
                window_1m = df_1m.iloc[: replay_index + 1]
                df_5m = self._resample(window_1m, "5min")
                df_15m = self._resample(window_1m, "15min")
                if len(df_5m) < 50 or len(df_15m) < 20:
                    continue

                recommendation = recommender.generate_recommendation(df_1m=window_1m, df_5m=df_5m, df_15m=df_15m, symbol=symbol)
                if recommendation is None:
                    continue

                historical_time = window_1m.index[-1].to_pydatetime() if hasattr(window_1m.index[-1], "to_pydatetime") else window_1m.index[-1]
                recommendation.generated_at = historical_time
                recommendation.data_status = "stale"
                current_bar = window_1m.iloc[-1]

                if active_position is not None:
                    exit_event = self._check_position_exit(active_position, current_bar, historical_time)
                    if exit_event is not None:
                        await self._store_exit_item(run_id, replay_index, symbol, exit_event)
                        total_signals += 1
                        stored_items.append(exit_event)
                        active_position = None
                        last_signature = None
                        continue

                if active_position is not None and recommendation.recommendation == active_position["direction"]:
                    active_position = self._refresh_position(active_position, recommendation)
                    continue

                if active_position is not None and recommendation.recommendation in {"BUY", "SELL"} and recommendation.recommendation != active_position["direction"]:
                    flip_event = self._build_exit_event(active_position, "signal_flip", recommendation.current_price, historical_time, recommendation.current_price)
                    await self._store_exit_item(run_id, replay_index, symbol, flip_event)
                    total_signals += 1
                    stored_items.append(flip_event)
                    active_position = None
                    last_signature = None
                    continue

                signature = self._build_signature(recommendation)
                if not self._should_store(recommendation, last_signature):
                    continue
                app_payload = recommendation.model_dump(mode="json")
                ai_payload = None
                ai_applied = False

                if include_ai and settings.ai_enabled and ai_service and recommendation.recommendation in {"BUY", "SELL"}:
                    ai_payload = await self._enrich_with_ai(ai_service, recommendation, window_1m)
                    ai_applied = ai_payload is not None

                await self._store_item(
                    run_id=run_id,
                    replay_index=replay_index,
                    recommendation=recommendation,
                    app_payload=app_payload,
                    ai_payload=ai_payload,
                    ai_applied=ai_applied,
                )
                total_signals += 1
                last_signature = signature
                if recommendation.recommendation in {"BUY", "SELL"}:
                    active_position = self._create_position_snapshot(recommendation)
                stored_items.append(
                    {
                        "signal_id": recommendation.signal_id,
                        "generated_at": recommendation.generated_at.isoformat(),
                        "recommendation": recommendation.recommendation,
                        "confidence": recommendation.confidence,
                        "current_price": recommendation.current_price,
                        "ai_applied": ai_applied,
                        "app_recommendation": app_payload,
                        "ai_recommendation": ai_payload,
                    }
                )

            await self._complete_run(run_id, total_signals, "completed")
            logger.info(f"Recommendation replay completed for {symbol}: {total_signals} stored signals")
            return {
                "run_id": run_id,
                "symbol": symbol,
                "provider": provider,
                "start_date": start_date,
                "end_date": end_date,
                "include_ai": include_ai,
                "total_signals": total_signals,
                "items": stored_items[-100:],
            }
        except Exception as exc:
            await self._complete_run(run_id, total_signals, "failed")
            logger.error(f"Recommendation replay failed: {exc}")
            raise

    async def run_replay(
        self,
        symbol: str,
        provider: str,
        start_date: str,
        end_date: str,
        settings: StrategySettings,
        recommender: SignalRecommenderEngine,
        ai_service,
        df_1m: pd.DataFrame,
        include_ai: bool = True,
    ) -> dict[str, Any]:
        run_id = await self.create_run(symbol, provider, start_date, end_date, include_ai)
        return await self.execute_replay(
            run_id=run_id,
            symbol=symbol,
            provider=provider,
            start_date=start_date,
            end_date=end_date,
            settings=settings,
            recommender=recommender,
            ai_service=ai_service,
            df_1m=df_1m,
            include_ai=include_ai,
        )

    async def get_history(self, limit: int = 100, run_id: int | None = None) -> dict[str, Any]:
        query = [
            """
            SELECT i.*, r.symbol AS run_symbol, r.provider, r.start_date, r.end_date, r.include_ai
            FROM recommendation_replay_items i
            JOIN recommendation_replay_runs r ON r.id = i.run_id
            """
        ]
        params: list[Any] = []
        if run_id is not None:
            query.append("WHERE i.run_id = ?")
            params.append(run_id)
        query.append("ORDER BY i.generated_at DESC, i.id DESC")
        query.append("LIMIT ?")
        params.append(limit)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("\n".join(query), tuple(params)) as cursor:
                rows = await cursor.fetchall()
            async with db.execute(
                """
                SELECT *
                FROM recommendation_replay_runs
                ORDER BY created_at DESC, id DESC
                LIMIT 20
                """
            ) as cursor:
                run_rows = await cursor.fetchall()

        return {
            "items": [self._serialize_item(row) for row in rows],
            "runs": [self._serialize_run(row) for row in run_rows],
        }

    async def _create_run(self, symbol: str, provider: str, start_date: str, end_date: str, include_ai: bool) -> int:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO recommendation_replay_runs (
                    symbol, provider, start_date, end_date, include_ai, status, total_signals, created_at
                )
                VALUES (?, ?, ?, ?, ?, 'running', 0, ?)
                """,
                (symbol, provider, start_date, end_date, 1 if include_ai else 0, now),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def _store_item(
        self,
        run_id: int,
        replay_index: int,
        recommendation: SignalRecommendation,
        app_payload: dict[str, Any],
        ai_payload: dict[str, Any] | None,
        ai_applied: bool,
    ) -> None:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO recommendation_replay_items (
                    run_id, replay_index, signal_id, symbol, recommendation, confidence,
                    generated_at, current_price, ai_applied, app_payload, ai_payload, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    replay_index,
                    recommendation.signal_id,
                    recommendation.symbol,
                    recommendation.recommendation,
                    float(recommendation.confidence),
                    recommendation.generated_at.isoformat(),
                    float(recommendation.current_price),
                    1 if ai_applied else 0,
                    json.dumps(app_payload),
                    json.dumps(ai_payload) if ai_payload else None,
                    now,
                ),
            )
            await db.commit()

    async def _store_exit_item(
        self,
        run_id: int,
        replay_index: int,
        symbol: str,
        event: dict[str, Any],
    ) -> None:
        now = datetime.utcnow().isoformat()
        payload = event["app_recommendation"]
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO recommendation_replay_items (
                    run_id, replay_index, signal_id, symbol, recommendation, confidence,
                    generated_at, current_price, ai_applied, app_payload, ai_payload, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, NULL, ?)
                """,
                (
                    run_id,
                    replay_index,
                    event["signal_id"],
                    symbol,
                    event["recommendation"],
                    float(event["confidence"]),
                    event["generated_at"],
                    float(event["current_price"]),
                    json.dumps(payload),
                    now,
                ),
            )
            await db.commit()

    async def _complete_run(self, run_id: int, total_signals: int, status: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE recommendation_replay_runs
                SET status = ?, total_signals = ?, completed_at = ?
                WHERE id = ?
                """,
                (status, total_signals, datetime.utcnow().isoformat(), run_id),
            )
            await db.commit()

    async def _enrich_with_ai(self, ai_service, recommendation: SignalRecommendation, df_1m: pd.DataFrame) -> dict[str, Any] | None:
        try:
            features_df = build_features(df_1m)
            if features_df.empty:
                return None
            latest_candle = features_df.iloc[-1].to_dict()
            base_payload = recommendation.model_dump(mode="json")
            user_prompt = build_recommendation_prompt(base_payload, latest_candle)
            ai_dict = await ai_service.llm.analyze_market(RECOMMENDATION_SYSTEM_PROMPT, user_prompt)
            if not ai_dict:
                return None
            enriched = dict(base_payload)
            raw_reasoning = ai_dict.get("reasoning")
            if isinstance(raw_reasoning, list) and raw_reasoning:
                enriched["reasoning"] = raw_reasoning
            elif isinstance(raw_reasoning, str) and raw_reasoning:
                enriched["reasoning"] = [raw_reasoning]
            if ai_dict.get("risk_note"):
                enriched["risk_note"] = ai_dict["risk_note"]
            enriched["ai_source"] = getattr(ai_service.llm, "provider", "").upper()
            return enriched
        except Exception as exc:
            logger.warning(f"AI replay enrichment failed: {exc}")
            return None

    @staticmethod
    def _resample(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        return (
            df.resample(timeframe)
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .dropna()
        )

    @staticmethod
    def _create_position_snapshot(recommendation: SignalRecommendation) -> dict[str, Any]:
        take_profit = recommendation.take_profit_targets[0] if recommendation.take_profit_targets else None
        return {
            "symbol": recommendation.symbol,
            "direction": recommendation.recommendation,
            "entry_price": float(recommendation.current_price),
            "stop_loss": float(recommendation.stop_loss) if recommendation.stop_loss is not None else None,
            "take_profit": float(take_profit) if take_profit is not None else None,
            "trailing_offset": float(recommendation.trailing_stop_offset) if recommendation.trailing_stop_offset is not None else None,
            "trail_high": float(recommendation.current_price),
            "trail_low": float(recommendation.current_price),
            "bias": recommendation.bias,
            "mtf_bias_15m": recommendation.mtf_bias_15m,
            "mtf_setup_5m": recommendation.mtf_setup_5m,
            "exit_strategy": recommendation.exit_strategy,
        }

    @staticmethod
    def _refresh_position(position: dict[str, Any], recommendation: SignalRecommendation) -> dict[str, Any]:
        updated = dict(position)
        next_stop = float(recommendation.stop_loss) if recommendation.stop_loss is not None else None
        if next_stop is not None:
            if updated["direction"] == "BUY":
                updated["stop_loss"] = max(updated.get("stop_loss") or next_stop, next_stop)
            else:
                updated["stop_loss"] = min(updated.get("stop_loss") or next_stop, next_stop)
        take_profit = recommendation.take_profit_targets[0] if recommendation.take_profit_targets else None
        if take_profit is not None:
            updated["take_profit"] = float(take_profit)
        if recommendation.trailing_stop_offset is not None:
            updated["trailing_offset"] = float(recommendation.trailing_stop_offset)
        return updated

    @staticmethod
    def _check_position_exit(position: dict[str, Any], current_bar: pd.Series, event_time: datetime) -> dict[str, Any] | None:
        high = float(current_bar["high"])
        low = float(current_bar["low"])
        direction = position["direction"]
        stop_loss = position.get("stop_loss")
        take_profit = position.get("take_profit")
        trailing_offset = position.get("trailing_offset")

        if direction == "BUY":
            position["trail_high"] = max(float(position.get("trail_high") or position["entry_price"]), high)
            if trailing_offset:
                candidate = position["trail_high"] - float(trailing_offset)
                stop_loss = candidate if stop_loss is None else max(float(stop_loss), candidate)
                position["stop_loss"] = stop_loss
            if stop_loss is not None and low <= float(stop_loss):
                reason = "atr_trailing_stop" if trailing_offset else "stop_loss"
                return RecommendationHistoryService._build_exit_event(position, reason, float(stop_loss), event_time, float(current_bar["close"]))
            if take_profit is not None and high >= float(take_profit):
                return RecommendationHistoryService._build_exit_event(position, "take_profit", float(take_profit), event_time, float(current_bar["close"]))
        else:
            position["trail_low"] = min(float(position.get("trail_low") or position["entry_price"]), low)
            if trailing_offset:
                candidate = position["trail_low"] + float(trailing_offset)
                stop_loss = candidate if stop_loss is None else min(float(stop_loss), candidate)
                position["stop_loss"] = stop_loss
            if stop_loss is not None and high >= float(stop_loss):
                reason = "atr_trailing_stop" if trailing_offset else "stop_loss"
                return RecommendationHistoryService._build_exit_event(position, reason, float(stop_loss), event_time, float(current_bar["close"]))
            if take_profit is not None and low <= float(take_profit):
                return RecommendationHistoryService._build_exit_event(position, "take_profit", float(take_profit), event_time, float(current_bar["close"]))
        return None

    @staticmethod
    def _build_exit_event(
        position: dict[str, Any],
        reason: str,
        exit_price: float,
        event_time: datetime,
        current_price: float,
    ) -> dict[str, Any]:
        direction = position["direction"]
        multiplier = 1 if direction == "BUY" else -1
        pnl_points = (exit_price - float(position["entry_price"])) * multiplier
        recommendation = reason.upper()
        payload = {
            "signal_id": f"EXIT-{event_time.strftime('%Y%m%d%H%M%S%f')}",
            "symbol": position["symbol"],
            "timeframe": "REPLAY_EXIT",
            "recommendation": recommendation,
            "bias": position.get("bias", "NEUTRAL"),
            "mtf_bias_15m": position.get("mtf_bias_15m", "NEUTRAL"),
            "mtf_setup_5m": position.get("mtf_setup_5m", "NEUTRAL"),
            "mtf_timing_1m": "EXIT",
            "confidence": 100.0,
            "current_price": round(current_price, 1),
            "entry_zone": None,
            "stop_loss": position.get("stop_loss"),
            "take_profit_targets": [position["take_profit"]] if position.get("take_profit") is not None else [],
            "exit_strategy": position.get("exit_strategy", ""),
            "trailing_stop_timeframe": "10m" if position.get("trailing_offset") else "",
            "trailing_stop_atr_period": 14,
            "trailing_stop_atr_multiplier": 2.0 if position.get("trailing_offset") else 0.0,
            "trailing_stop_atr": None,
            "trailing_stop_offset": position.get("trailing_offset"),
            "supports": [],
            "resistances": [],
            "nearest_fib_zone": "",
            "trend_short": direction,
            "trend_medium": direction,
            "momentum": "EXIT",
            "risk_reward_estimate": pnl_points,
            "reasoning": [
                f"{direction} position closed by {reason.replace('_', ' ')}.",
                f"Entry {position['entry_price']:,.1f} -> Exit {exit_price:,.1f}.",
            ],
            "risk_note": "",
            "data_status": "stale",
            "generated_at": event_time.isoformat(),
            "position_direction": direction,
            "entry_price": position["entry_price"],
            "exit_price": exit_price,
            "pnl_points": round(pnl_points, 1),
        }
        return {
            "signal_id": payload["signal_id"],
            "generated_at": event_time.isoformat(),
            "recommendation": recommendation,
            "confidence": 100.0,
            "current_price": round(current_price, 1),
            "ai_applied": False,
            "app_recommendation": payload,
            "ai_recommendation": None,
        }

    @staticmethod
    def _build_signature(recommendation: SignalRecommendation) -> tuple[Any, ...]:
        return (
            recommendation.recommendation,
            recommendation.bias,
            recommendation.mtf_setup_5m,
            recommendation.mtf_timing_1m,
            round(float(recommendation.confidence), 1),
        )

    @staticmethod
    def _should_store(recommendation: SignalRecommendation, last_signature: tuple[Any, ...] | None) -> bool:
        signature = RecommendationHistoryService._build_signature(recommendation)
        if recommendation.recommendation in {"BUY", "SELL"}:
            return True
        return signature != last_signature

    @staticmethod
    def _serialize_item(row: aiosqlite.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "replay_index": row["replay_index"],
            "signal_id": row["signal_id"],
            "symbol": row["symbol"],
            "recommendation": row["recommendation"],
            "confidence": row["confidence"],
            "generated_at": row["generated_at"],
            "current_price": row["current_price"],
            "ai_applied": bool(row["ai_applied"]),
            "app_recommendation": json.loads(row["app_payload"]) if row["app_payload"] else None,
            "ai_recommendation": json.loads(row["ai_payload"]) if row["ai_payload"] else None,
            "run_meta": {
                "symbol": row["run_symbol"],
                "provider": row["provider"],
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "include_ai": bool(row["include_ai"]),
            },
        }

    @staticmethod
    def _serialize_run(row: aiosqlite.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "symbol": row["symbol"],
            "provider": row["provider"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "include_ai": bool(row["include_ai"]),
            "status": row["status"],
            "total_signals": row["total_signals"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
        }
