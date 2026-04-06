from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

import aiosqlite
from pydantic import BaseModel, Field


class StrategySettings(BaseModel):
    symbol: str = "VN30F1M"
    provider: Literal["VCI", "KBS"] = "VCI"
    analysis_interval_sec: int = 900
    history_window_days: int = 30
    history_sync_interval_sec: int = 1800
    ai_enabled: bool = True
    ai_model: str = "gemini"
    min_confidence: float = 65.0
    risk_per_trade_pct: float = 1.0
    initial_capital: float = 100_000_000.0
    max_open_positions: int = 1
    slippage_bps: float = 5.0
    fee_bps: float = 3.0
    allow_short: bool = True
    auto_journal_signals: bool = True
    trailing_stop_timeframe: str = "10m"
    trailing_stop_atr_period: int = 14
    trailing_stop_atr_multiplier: float = 2.0
    notes: str = ""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StrategySettingsService:
    def __init__(self, db_path: str = "market_data.db"):
        self.db_path = db_path

    async def init_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await db.commit()

    async def get_settings(self) -> StrategySettings:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT payload FROM strategy_settings WHERE id = 1"
            ) as cursor:
                row = await cursor.fetchone()

            if not row:
                settings = StrategySettings()
                await self.save_settings(settings)
                return settings

            payload = json.loads(row[0])
            return StrategySettings.model_validate(payload)

    async def save_settings(self, settings: StrategySettings) -> StrategySettings:
        payload = settings.model_dump(mode="json")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO strategy_settings (id, payload, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (
                    json.dumps(payload),
                    settings.updated_at.isoformat(),
                ),
            )
            await db.commit()
        return settings

    async def update_settings(self, patch: dict[str, Any]) -> StrategySettings:
        current = await self.get_settings()
        updated = current.model_copy(
            update={**patch, "updated_at": datetime.now(timezone.utc)}
        )
        return await self.save_settings(updated)
