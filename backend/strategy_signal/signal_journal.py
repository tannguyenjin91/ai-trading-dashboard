from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiosqlite

from shared.models import SignalRecommendation
from strategy_signal.strategy_settings import StrategySettings


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SignalJournalService:
    def __init__(self, db_path: str = "market_data.db"):
        self.db_path = db_path

    async def init_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS signal_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    current_price REAL NOT NULL,
                    exit_price REAL,
                    quantity REAL NOT NULL,
                    stop_loss REAL,
                    take_profit REAL,
                    confidence REAL NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    close_reason TEXT,
                    realized_pnl REAL NOT NULL DEFAULT 0,
                    unrealized_pnl REAL NOT NULL DEFAULT 0,
                    recommendation_payload TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS signal_order_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER,
                    signal_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_time TEXT NOT NULL,
                    status TEXT NOT NULL,
                    price REAL,
                    pnl REAL NOT NULL DEFAULT 0,
                    details_payload TEXT NOT NULL
                )
                """
            )
            await self._ensure_order_columns(db)
            await db.commit()

    async def sync_market_price(
        self,
        symbol: str,
        price: float,
        timestamp: Optional[datetime] = None,
    ) -> None:
        now = (timestamp or _utc_now()).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT *
                FROM signal_orders
                WHERE symbol = ? AND status = 'OPEN'
                ORDER BY opened_at ASC
                """,
                (symbol,),
            ) as cursor:
                rows = await cursor.fetchall()

            for row in rows:
                direction = row["direction"]
                quantity = float(row["quantity"] or 0)
                entry_price = float(row["entry_price"] or 0)
                take_profit = self._as_float(row["take_profit"])
                trailing_offset = self._as_float(row["trailing_offset"])
                stop_loss = self._as_float(row["stop_loss"])
                trail_high = self._as_float(row["trail_high"], entry_price)
                trail_low = self._as_float(row["trail_low"], entry_price)

                if direction == "BUY":
                    trail_high = max(trail_high, price)
                else:
                    trail_low = min(trail_low, price)

                if trailing_offset is not None and trailing_offset > 0:
                    stop_loss = self._apply_trailing_stop(direction, stop_loss, trail_high, trail_low, trailing_offset)

                unrealized = self._calculate_pnl(direction, entry_price, price, quantity)
                close_reason = None
                exit_price = None
                if stop_loss is not None:
                    if direction == "BUY" and price <= float(stop_loss):
                        close_reason = "atr_trailing_stop" if trailing_offset else "stop_loss"
                        exit_price = float(stop_loss)
                    elif direction == "SELL" and price >= float(stop_loss):
                        close_reason = "atr_trailing_stop" if trailing_offset else "stop_loss"
                        exit_price = float(stop_loss)

                if close_reason is None and take_profit is not None:
                    if direction == "BUY" and price >= float(take_profit):
                        close_reason = "take_profit"
                        exit_price = float(take_profit)
                    elif direction == "SELL" and price <= float(take_profit):
                        close_reason = "take_profit"
                        exit_price = float(take_profit)

                if close_reason and exit_price is not None:
                    realized = self._calculate_pnl(direction, entry_price, exit_price, quantity)
                    await db.execute(
                        """
                        UPDATE signal_orders
                        SET status = 'CLOSED',
                            current_price = ?,
                            exit_price = ?,
                            closed_at = ?,
                            close_reason = ?,
                            stop_loss = ?,
                            trailing_stop = ?,
                            trail_high = ?,
                            trail_low = ?,
                            realized_pnl = ?,
                            unrealized_pnl = 0
                        WHERE id = ?
                        """,
                        (price, exit_price, now, close_reason, stop_loss, stop_loss, trail_high, trail_low, realized, row["id"]),
                    )
                    await self._append_event(
                        db=db,
                        order_id=row["id"],
                        signal_id=row["signal_id"],
                        symbol=row["symbol"],
                        event_type="CLOSE",
                        event_time=now,
                        status="CLOSED",
                        price=exit_price,
                        pnl=realized,
                        details={
                            "close_reason": close_reason,
                            "entry_price": entry_price,
                            "exit_price": exit_price,
                            "quantity": quantity,
                            "stop_loss": stop_loss,
                            "trailing_offset": trailing_offset,
                            "exit_strategy": row["exit_strategy"],
                        },
                    )
                else:
                    await db.execute(
                        """
                        UPDATE signal_orders
                        SET current_price = ?,
                            stop_loss = ?,
                            trailing_stop = ?,
                            trail_high = ?,
                            trail_low = ?,
                            unrealized_pnl = ?
                        WHERE id = ?
                        """,
                        (price, stop_loss, stop_loss, trail_high, trail_low, unrealized, row["id"]),
                    )
                    await self._append_event(
                        db=db,
                        order_id=row["id"],
                        signal_id=row["signal_id"],
                        symbol=row["symbol"],
                        event_type="MARK_TO_MARKET",
                        event_time=now,
                        status="OPEN",
                        price=price,
                        pnl=unrealized,
                        details={
                            "entry_price": entry_price,
                            "quantity": quantity,
                            "stop_loss": stop_loss,
                            "trailing_offset": trailing_offset,
                            "trail_high": trail_high,
                            "trail_low": trail_low,
                            "exit_strategy": row["exit_strategy"],
                        },
                    )

            await db.commit()

    async def record_recommendation(
        self,
        recommendation: SignalRecommendation,
        settings: StrategySettings,
    ) -> Optional[dict[str, Any]]:
        await self.sync_market_price(
            recommendation.symbol,
            recommendation.current_price,
            recommendation.generated_at,
        )

        if not settings.auto_journal_signals:
            return None
        if recommendation.recommendation not in {"BUY", "SELL"}:
            return None
        if recommendation.confidence < settings.min_confidence:
            return None
        if recommendation.recommendation == "SELL" and not settings.allow_short:
            return None

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT *
                FROM signal_orders
                WHERE symbol = ? AND status = 'OPEN'
                ORDER BY opened_at ASC
                """,
                (recommendation.symbol,),
            ) as cursor:
                open_positions = await cursor.fetchall()

            current_direction = recommendation.recommendation
            same_direction = [row for row in open_positions if row["direction"] == current_direction]
            opposite = [row for row in open_positions if row["direction"] != current_direction]
            new_stop_loss = recommendation.stop_loss
            new_take_profit = recommendation.take_profit_targets[0] if recommendation.take_profit_targets else None
            new_trailing_offset = recommendation.trailing_stop_offset

            for row in opposite:
                realized = self._calculate_pnl(
                    row["direction"],
                    float(row["entry_price"]),
                    recommendation.current_price,
                    float(row["quantity"]),
                )
                await db.execute(
                    """
                    UPDATE signal_orders
                    SET status = 'CLOSED',
                        current_price = ?,
                        exit_price = ?,
                        closed_at = ?,
                        close_reason = 'signal_flip',
                        realized_pnl = ?,
                        unrealized_pnl = 0
                    WHERE id = ?
                    """,
                    (
                        recommendation.current_price,
                        recommendation.current_price,
                        recommendation.generated_at.isoformat(),
                        realized,
                        row["id"],
                    ),
                )
                await self._append_event(
                    db=db,
                    order_id=row["id"],
                    signal_id=row["signal_id"],
                    symbol=row["symbol"],
                    event_type="CLOSE",
                    event_time=recommendation.generated_at.isoformat(),
                    status="CLOSED",
                    price=recommendation.current_price,
                    pnl=realized,
                    details={
                        "close_reason": "signal_flip",
                        "entry_price": float(row["entry_price"]),
                        "exit_price": recommendation.current_price,
                        "quantity": float(row["quantity"]),
                    },
                )

            if same_direction:
                row = same_direction[0]
                await db.execute(
                    """
                    UPDATE signal_orders
                    SET current_price = ?,
                        stop_loss = ?,
                        trailing_stop = ?,
                        trailing_offset = ?,
                        take_profit = ?,
                        confidence = ?,
                        exit_strategy = ?,
                        recommendation_payload = ?,
                        unrealized_pnl = ?
                    WHERE id = ?
                    """,
                    (
                        recommendation.current_price,
                        self._merge_stop_loss(row["direction"], self._as_float(row["stop_loss"]), new_stop_loss),
                        self._merge_stop_loss(row["direction"], self._as_float(row["trailing_stop"]), new_stop_loss),
                        new_trailing_offset if new_trailing_offset is not None else self._as_float(row["trailing_offset"]),
                        new_take_profit,
                        recommendation.confidence,
                        recommendation.exit_strategy or row["exit_strategy"] or "fixed_sl_tp",
                        json.dumps(recommendation.model_dump(mode="json")),
                        self._calculate_pnl(
                            row["direction"],
                            float(row["entry_price"]),
                            recommendation.current_price,
                            float(row["quantity"]),
                        ),
                        row["id"],
                    ),
                )
                await self._append_event(
                    db=db,
                    order_id=row["id"],
                    signal_id=row["signal_id"],
                    symbol=row["symbol"],
                    event_type="ADJUST",
                    event_time=recommendation.generated_at.isoformat(),
                    status="OPEN",
                    price=recommendation.current_price,
                    pnl=self._calculate_pnl(
                        row["direction"],
                        float(row["entry_price"]),
                        recommendation.current_price,
                        float(row["quantity"]),
                    ),
                    details={
                        "stop_loss": self._merge_stop_loss(row["direction"], self._as_float(row["stop_loss"]), new_stop_loss),
                        "take_profit": new_take_profit,
                        "trailing_offset": new_trailing_offset if new_trailing_offset is not None else self._as_float(row["trailing_offset"]),
                        "exit_strategy": recommendation.exit_strategy or row["exit_strategy"] or "fixed_sl_tp",
                        "confidence": recommendation.confidence,
                    },
                )
                await db.commit()
                return await self.get_position_by_id(row["id"])

            if len(open_positions) - len(opposite) >= settings.max_open_positions:
                await db.commit()
                return None

            entry_price = recommendation.current_price
            risk_per_unit = abs(entry_price - (recommendation.stop_loss or entry_price * 0.995))
            capital_at_risk = settings.initial_capital * max(settings.risk_per_trade_pct, 0.1) / 100
            quantity = max(1, math.floor(capital_at_risk / max(risk_per_unit, entry_price * 0.0025)))
            take_profit = recommendation.take_profit_targets[0] if recommendation.take_profit_targets else None
            trailing_offset = recommendation.trailing_stop_offset
            exit_strategy = recommendation.exit_strategy or "fixed_sl_tp"

            cursor = await db.execute(
                """
                INSERT INTO signal_orders (
                    signal_id,
                    symbol,
                    direction,
                    status,
                    entry_price,
                    current_price,
                    quantity,
                    stop_loss,
                    take_profit,
                    confidence,
                    opened_at,
                    recommendation_payload,
                    exit_strategy,
                    trailing_stop,
                    trailing_offset,
                    trail_high,
                    trail_low
                )
                VALUES (?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recommendation.signal_id,
                    recommendation.symbol,
                    current_direction,
                    entry_price,
                    recommendation.current_price,
                    quantity,
                    recommendation.stop_loss,
                    take_profit,
                    recommendation.confidence,
                    recommendation.generated_at.isoformat(),
                    json.dumps(recommendation.model_dump(mode="json")),
                    exit_strategy,
                    recommendation.stop_loss,
                    trailing_offset,
                    entry_price,
                    entry_price,
                ),
            )
            order_id = cursor.lastrowid
            await self._append_event(
                db=db,
                order_id=order_id,
                signal_id=recommendation.signal_id,
                symbol=recommendation.symbol,
                event_type="OPEN",
                event_time=recommendation.generated_at.isoformat(),
                status="OPEN",
                price=recommendation.current_price,
                pnl=0,
                details={
                    "direction": current_direction,
                    "entry_price": entry_price,
                    "quantity": quantity,
                    "stop_loss": recommendation.stop_loss,
                    "take_profit": take_profit,
                    "trailing_offset": trailing_offset,
                    "exit_strategy": exit_strategy,
                    "confidence": recommendation.confidence,
                },
            )
            await db.commit()

        return await self.get_position_by_id(order_id)

    async def get_position_by_id(self, order_id: int) -> Optional[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM signal_orders WHERE id = ?",
                (order_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return self._serialize_row(row) if row else None

    async def get_open_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        query = [
            "SELECT * FROM signal_orders WHERE status = 'OPEN'",
        ]
        params: list[Any] = []
        if symbol:
            query.append("AND symbol = ?")
            params.append(symbol)
        query.append("ORDER BY opened_at ASC")
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(" ".join(query), tuple(params)) as cursor:
                rows = await cursor.fetchall()
        return [self._serialize_row(row) for row in rows]

    async def close_open_positions(
        self,
        symbol: str,
        exit_price: float,
        event_time: datetime,
        close_reason: str,
    ) -> list[dict[str, Any]]:
        closed_positions: list[dict[str, Any]] = []
        event_time_iso = event_time.isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT *
                FROM signal_orders
                WHERE symbol = ? AND status = 'OPEN'
                ORDER BY opened_at ASC
                """,
                (symbol,),
            ) as cursor:
                rows = await cursor.fetchall()

            for row in rows:
                entry_price = float(row["entry_price"] or 0)
                quantity = float(row["quantity"] or 0)
                realized = self._calculate_pnl(row["direction"], entry_price, exit_price, quantity)
                await db.execute(
                    """
                    UPDATE signal_orders
                    SET status = 'CLOSED',
                        current_price = ?,
                        exit_price = ?,
                        closed_at = ?,
                        close_reason = ?,
                        realized_pnl = ?,
                        unrealized_pnl = 0
                    WHERE id = ?
                    """,
                    (
                        exit_price,
                        exit_price,
                        event_time_iso,
                        close_reason,
                        realized,
                        row["id"],
                    ),
                )
                await self._append_event(
                    db=db,
                    order_id=row["id"],
                    signal_id=row["signal_id"],
                    symbol=row["symbol"],
                    event_type="CLOSE",
                    event_time=event_time_iso,
                    status="CLOSED",
                    price=exit_price,
                    pnl=realized,
                    details={
                        "close_reason": close_reason,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "quantity": quantity,
                        "exit_strategy": row["exit_strategy"],
                    },
                )
                closed_positions.append(
                    {
                        **self._serialize_row(row),
                        "status": "CLOSED",
                        "current_price": exit_price,
                        "exit_price": exit_price,
                        "closed_at": event_time_iso,
                        "close_reason": close_reason,
                        "realized_pnl": realized,
                        "unrealized_pnl": 0,
                    }
                )

            await db.commit()

        return closed_positions

    async def get_portfolio_summary(
        self,
        settings: StrategySettings,
        limit: int = 20,
        days: int = 30,
    ) -> dict[str, Any]:
        cutoff = (_utc_now() - timedelta(days=max(days, 1))).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM signal_orders WHERE status = 'OPEN' ORDER BY opened_at DESC"
            ) as open_cursor:
                open_rows = await open_cursor.fetchall()

            async with db.execute(
                """
                SELECT *
                FROM signal_orders
                WHERE status = 'CLOSED'
                  AND COALESCE(closed_at, opened_at) >= ?
                ORDER BY closed_at DESC
                LIMIT ?
                """,
                (cutoff, limit),
            ) as closed_cursor:
                closed_rows = await closed_cursor.fetchall()

        open_positions = [self._serialize_row(row) for row in open_rows]
        closed_positions = [self._serialize_row(row) for row in closed_rows]

        realized_pnl = sum(float(item["realized_pnl"] or 0) for item in closed_positions)
        unrealized_pnl = sum(float(item["unrealized_pnl"] or 0) for item in open_positions)
        winning_trades = [item for item in closed_positions if float(item["realized_pnl"] or 0) > 0]
        balance = settings.initial_capital + realized_pnl
        equity = balance + unrealized_pnl

        return {
            "mode": "signal_only",
            "symbol": settings.symbol,
            "starting_capital": settings.initial_capital,
            "balance": balance,
            "equity": equity,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "open_positions": open_positions,
            "history": closed_positions,
            "open_count": len(open_positions),
            "closed_count": len(closed_positions),
            "win_rate": (len(winning_trades) / len(closed_positions) * 100) if closed_positions else 0.0,
            "window_days": days,
        }

    async def get_order_history(self, limit: int = 50, days: int = 30) -> dict[str, Any]:
        cutoff = (_utc_now() - timedelta(days=max(days, 1))).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT *
                FROM signal_orders
                WHERE COALESCE(closed_at, opened_at) >= ?
                ORDER BY COALESCE(closed_at, opened_at) DESC
                LIMIT ?
                """,
                (cutoff, limit),
            ) as cursor:
                rows = await cursor.fetchall()

            async with db.execute(
                """
                SELECT *
                FROM signal_order_events
                WHERE event_time >= ?
                ORDER BY event_time DESC
                LIMIT ?
                """,
                (cutoff, limit * 4),
            ) as cursor:
                event_rows = await cursor.fetchall()

        return {
            "window_days": days,
            "orders": [self._serialize_row(row) for row in rows],
            "events": [self._serialize_event(row) for row in event_rows],
        }

    async def _ensure_order_columns(self, db: aiosqlite.Connection) -> None:
        async with db.execute("PRAGMA table_info(signal_orders)") as cursor:
            rows = await cursor.fetchall()
        columns = {row[1] for row in rows}
        required = {
            "exit_strategy": "TEXT DEFAULT 'fixed_sl_tp'",
            "trailing_stop": "REAL",
            "trailing_offset": "REAL",
            "trail_high": "REAL",
            "trail_low": "REAL",
        }
        for column, definition in required.items():
            if column not in columns:
                await db.execute(f"ALTER TABLE signal_orders ADD COLUMN {column} {definition}")

    @staticmethod
    def _as_float(value: Any, default: float | None = None) -> float | None:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _merge_stop_loss(direction: str, existing: float | None, proposed: float | None) -> float | None:
        if proposed is None:
            return existing
        if existing is None:
            return proposed
        return max(existing, proposed) if direction == "BUY" else min(existing, proposed)

    @staticmethod
    def _apply_trailing_stop(
        direction: str,
        current_stop: float | None,
        trail_high: float,
        trail_low: float,
        trailing_offset: float,
    ) -> float | None:
        candidate = trail_high - trailing_offset if direction == "BUY" else trail_low + trailing_offset
        if current_stop is None:
            return candidate
        return max(current_stop, candidate) if direction == "BUY" else min(current_stop, candidate)

    async def _append_event(
        self,
        db: aiosqlite.Connection,
        order_id: int,
        signal_id: str,
        symbol: str,
        event_type: str,
        event_time: str,
        status: str,
        price: float | None,
        pnl: float,
        details: dict[str, Any],
    ) -> None:
        await db.execute(
            """
            INSERT INTO signal_order_events (
                order_id,
                signal_id,
                symbol,
                event_type,
                event_time,
                status,
                price,
                pnl,
                details_payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                signal_id,
                symbol,
                event_type,
                event_time,
                status,
                price,
                pnl,
                json.dumps(details),
            ),
        )

    @staticmethod
    def _calculate_pnl(direction: str, entry_price: float, current_price: float, quantity: float) -> float:
        multiplier = 1 if direction == "BUY" else -1
        return (current_price - entry_price) * quantity * multiplier

    @staticmethod
    def _serialize_row(row: aiosqlite.Row | None) -> Optional[dict[str, Any]]:
        if row is None:
            return None
        payload = {}
        if row["recommendation_payload"]:
            payload = json.loads(row["recommendation_payload"])
        return {
            "id": row["id"],
            "signal_id": row["signal_id"],
            "symbol": row["symbol"],
            "direction": row["direction"],
            "status": row["status"],
            "entry_price": row["entry_price"],
            "current_price": row["current_price"],
            "exit_price": row["exit_price"],
            "quantity": row["quantity"],
            "stop_loss": row["stop_loss"],
            "take_profit": row["take_profit"],
            "exit_strategy": row["exit_strategy"],
            "trailing_stop": row["trailing_stop"],
            "trailing_offset": row["trailing_offset"],
            "confidence": row["confidence"],
            "opened_at": row["opened_at"],
            "closed_at": row["closed_at"],
            "close_reason": row["close_reason"],
            "realized_pnl": row["realized_pnl"],
            "unrealized_pnl": row["unrealized_pnl"],
            "recommendation": payload,
        }

    @staticmethod
    def _serialize_event(row: aiosqlite.Row | None) -> Optional[dict[str, Any]]:
        if row is None:
            return None
        payload = {}
        if row["details_payload"]:
            payload = json.loads(row["details_payload"])
        return {
            "id": row["id"],
            "order_id": row["order_id"],
            "signal_id": row["signal_id"],
            "symbol": row["symbol"],
            "event_type": row["event_type"],
            "event_time": row["event_time"],
            "status": row["status"],
            "price": row["price"],
            "pnl": row["pnl"],
            "details": payload,
        }
