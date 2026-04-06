import asyncio
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import redis.asyncio as aioredis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from agent.prompt import RECOMMENDATION_SYSTEM_PROMPT, build_recommendation_prompt
from api.market_api import router as market_router
from api.monitor import router as monitor_router
from config.logging import setup_logging
from config.settings import settings
from data.feature_store import FeatureStoreService
from data.market_cache import LiveMarketCache
from data.realtime_feed import RealtimeMarketFeed
from data.store import DiskDataStore
from data.vnstock_service import VnstockDataIngestionService
from indicators.engine import build_features
from monitoring.audit_log import AuditLogger
from monitoring.system_monitor import SystemMonitor
from monitoring.telegram_bot import TelegramNotifier
from strategy_signal.ai_reasoner import AIReasoningService
from strategy_signal.backtest_service import BacktestService
from strategy_signal.recommender import SignalRecommenderEngine
from strategy_signal.signal_journal import SignalJournalService
from strategy_signal.recommendation_history import RecommendationHistoryService
from strategy_signal.strategy_settings import StrategySettingsService


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected - total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected - total: {len(self.active_connections)}")

    async def broadcast(self, data: dict) -> None:
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                dead.append(connection)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


def record_recommendation(app: FastAPI, recommendation: dict[str, Any]) -> None:
    if not hasattr(app.state, "recommendation_feed"):
        app.state.recommendation_feed = deque(maxlen=50)
    app.state.latest_recommendation = recommendation
    app.state.recommendation_feed.appendleft(recommendation)


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if df.empty:
        return df
    return (
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


async def persist_recent_bars(app: FastAPI, symbol: str, df: pd.DataFrame, timeframe: str) -> None:
    for timestamp, row in df.tail(120).iterrows():
        await app.state.store.save_candle(
            symbol=symbol,
            timestamp=timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp,
            ohlcv={
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(float(row.get("volume", 0) or 0)),
            },
            timeframe=timeframe,
        )


async def sync_symbol_history(app: FastAPI, symbol: str, provider: str, history_days: int) -> dict[str, Any]:
    coverage_before = await app.state.store.get_coverage(symbol, "1m")
    fetched = await app.state.vnstock_service.backfill_recent_data(
        symbol=symbol,
        days=history_days,
        timeframe="1m",
        source=provider,
    )
    daily_fetched = await app.state.vnstock_service.backfill_recent_data(
        symbol=symbol,
        days=max(history_days, 90),
        timeframe="1D",
        source=provider,
    )
    df_1m = await app.state.store.get_candles_range(
        symbol=symbol,
        timeframe="1m",
        start=(datetime.now() - pd.Timedelta(days=max(history_days, 1))).strftime("%Y-%m-%d %H:%M:%S"),
        end=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    if not df_1m.empty:
        await persist_recent_bars(app, symbol, resample_ohlcv(df_1m, "5min"), "5m")
        await persist_recent_bars(app, symbol, resample_ohlcv(df_1m, "15min"), "15m")
    coverage_after = await app.state.store.get_coverage(symbol, "1m")
    return {
        "symbol": symbol,
        "provider": provider,
        "history_days": history_days,
        "fetched_rows": fetched,
        "daily_fetched_rows": daily_fetched,
        "coverage_before": coverage_before,
        "coverage_after": coverage_after,
    }


async def run_ai_insight_loop(app: FastAPI):
    await asyncio.sleep(10)
    while True:
        sleep_for = 300
        try:
            if getattr(app.state.monitor, "is_kill_switch_active", False):
                await asyncio.sleep(30)
                continue
            current_settings = await app.state.strategy_settings.get_settings()
            symbol = current_settings.symbol
            app.state.feed.symbols = [symbol]
            sleep_for = max(current_settings.analysis_interval_sec, 300)

            df = await app.state.vnstock_service.fetch_history_df(
                symbol=symbol,
                timeframe="15m",
                limit=220,
                source=current_settings.provider,
            )
            if df.empty or len(df) < 30:
                logger.debug(f"AI insight skipped for {symbol}: insufficient vnstock bars")
                await asyncio.sleep(60)
                continue

            await persist_recent_bars(app, symbol, df, "15m")
            insight = await app.state.ai_service.generate_market_insight(df)
            if insight:
                insight["_data_source"] = f"vnstock:{current_settings.provider}"
                app.state.latest_insight = insight
                await manager.broadcast({"type": "AI_INSIGHT", "data": insight})
                await app.state.audit.log_event("AI_INSIGHT", symbol=symbol, details=insight)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error(f"AI insight loop error: {exc}")
            sleep_for = 60
        await asyncio.sleep(sleep_for)


async def run_recommendation_loop(app: FastAPI):
    await asyncio.sleep(12)
    while True:
        sleep_for = 300
        try:
            if getattr(app.state.monitor, "is_kill_switch_active", False):
                await asyncio.sleep(30)
                continue
            current_settings = await app.state.strategy_settings.get_settings()
            symbol = current_settings.symbol
            app.state.feed.symbols = [symbol]
            sleep_for = max(current_settings.analysis_interval_sec, 300)

            df_1m = await app.state.vnstock_service.fetch_history_df(
                symbol=symbol,
                timeframe="1m",
                limit=500,
                source=current_settings.provider,
            )
            if df_1m.empty or len(df_1m) < 200:
                logger.debug(f"Recommendation skipped for {symbol}: insufficient 1m bars")
                await asyncio.sleep(60)
                continue

            df_5m = resample_ohlcv(df_1m, "5min")
            df_15m = resample_ohlcv(df_1m, "15min")
            if len(df_5m) < 50 or len(df_15m) < 20:
                logger.debug(f"Recommendation skipped for {symbol}: resampled bars not ready")
                await asyncio.sleep(60)
                continue

            await persist_recent_bars(app, symbol, df_1m, "1m")
            await persist_recent_bars(app, symbol, df_5m, "5m")
            await persist_recent_bars(app, symbol, df_15m, "15m")

            recommendation = app.state.recommender_engine.generate_recommendation(df_1m, df_5m, df_15m, symbol)
            if recommendation is None:
                await asyncio.sleep(sleep_for)
                continue

            open_positions_before = await app.state.signal_journal.get_open_positions(symbol)
            await app.state.signal_journal.sync_market_price(
                symbol,
                recommendation.current_price,
                recommendation.generated_at,
            )
            current_open_positions = await app.state.signal_journal.get_open_positions(symbol)
            if current_open_positions:
                current_directions = {str(position["direction"]) for position in current_open_positions}
                if recommendation.recommendation in current_directions:
                    portfolio_snapshot = await app.state.signal_journal.get_portfolio_summary(current_settings, limit=10)
                    await manager.broadcast({"type": "PORTFOLIO_UPDATE", "data": portfolio_snapshot})
                    await asyncio.sleep(sleep_for)
                    continue

                if recommendation.recommendation in {"BUY", "SELL"} and current_directions and recommendation.recommendation not in current_directions:
                    await app.state.signal_journal.close_open_positions(
                        symbol=symbol,
                        exit_price=recommendation.current_price,
                        event_time=recommendation.generated_at,
                        close_reason="signal_flip",
                    )
                    portfolio_snapshot = await app.state.signal_journal.get_portfolio_summary(current_settings, limit=10)
                    await manager.broadcast({"type": "PORTFOLIO_UPDATE", "data": portfolio_snapshot})
                    await asyncio.sleep(sleep_for)
                    continue

            if open_positions_before and current_open_positions:
                portfolio_snapshot = await app.state.signal_journal.get_portfolio_summary(current_settings, limit=10)
                await manager.broadcast({"type": "PORTFOLIO_UPDATE", "data": portfolio_snapshot})
                await asyncio.sleep(sleep_for)
                continue

            if current_settings.ai_enabled and app.state.ai_service:
                try:
                    features_df = build_features(df_1m)
                    latest_candle = features_df.iloc[-1].to_dict()
                    user_prompt = build_recommendation_prompt(recommendation.model_dump(), latest_candle)
                    ai_dict = await app.state.ai_service.llm.analyze_market(RECOMMENDATION_SYSTEM_PROMPT, user_prompt)
                    if ai_dict:
                        raw_reasoning = ai_dict.get("reasoning")
                        if isinstance(raw_reasoning, list) and raw_reasoning:
                            recommendation.reasoning = raw_reasoning
                        elif isinstance(raw_reasoning, str) and raw_reasoning:
                            recommendation.reasoning = [raw_reasoning]
                        recommendation.risk_note = ai_dict.get("risk_note", recommendation.risk_note)
                except Exception as exc:
                    logger.warning(f"AI narrative enrichment failed: {exc}")

            payload = recommendation.model_dump(mode="json")
            record_recommendation(app, payload)
            await app.state.audit.log_event("SIGNAL_RECOMMENDATION", symbol=symbol, details=payload)

            journal_position = await app.state.signal_journal.record_recommendation(recommendation, current_settings)
            portfolio_snapshot = await app.state.signal_journal.get_portfolio_summary(current_settings, limit=10)

            await manager.broadcast({"type": "RECOMMENDATION", "data": payload})
            await manager.broadcast({"type": "PORTFOLIO_UPDATE", "data": portfolio_snapshot})
            if journal_position:
                await manager.broadcast({"type": "POSITION", "data": journal_position})

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error(f"Recommendation loop error: {exc}")
            sleep_for = 60
        await asyncio.sleep(sleep_for)


async def run_history_sync_loop(app: FastAPI):
    await asyncio.sleep(5)
    while True:
        sleep_for = 1800
        try:
            current_settings = await app.state.strategy_settings.get_settings()
            sleep_for = max(current_settings.history_sync_interval_sec, 300)
            sync_result = await sync_symbol_history(
                app=app,
                symbol=current_settings.symbol,
                provider=current_settings.provider,
                history_days=current_settings.history_window_days,
            )
            app.state.history_sync_status = {
                **sync_result,
                "synced_at": datetime.now(timezone.utc).isoformat(),
            }
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error(f"History sync loop error: {exc}")
            app.state.history_sync_status = {
                "error": str(exc),
                "synced_at": datetime.now(timezone.utc).isoformat(),
            }
            sleep_for = 300
        await asyncio.sleep(sleep_for)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    logger.info("Starting VN AI Signal Lab backend...")
    logger.info(f"Environment: {settings.environment.value} | Signal mode: only recommendations")

    try:
        app.state.redis = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        await app.state.redis.ping()
        logger.info("Redis connected")
    except Exception as exc:
        logger.warning(f"Redis unavailable: {exc}")
        app.state.redis = None

    app.state.store = DiskDataStore(db_path="market_data.db")
    await app.state.store.init_db()

    app.state.audit = AuditLogger(settings.database_url)
    await app.state.audit.init_db()

    app.state.strategy_settings = StrategySettingsService(db_path="market_data.db")
    await app.state.strategy_settings.init_db()
    current_settings = await app.state.strategy_settings.get_settings()

    app.state.signal_journal = SignalJournalService(db_path="market_data.db")
    await app.state.signal_journal.init_db()
    app.state.recommendation_history = RecommendationHistoryService(db_path="market_data.db")
    await app.state.recommendation_history.init_db()

    app.state.notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token.get_secret_value() if settings.telegram_bot_token else "",
        chat_id=settings.telegram_chat_id.get_secret_value() if settings.telegram_chat_id else "",
    )
    app.state.monitor = SystemMonitor(settings)
    app.state.market_cache = LiveMarketCache(stale_threshold_sec=2.0)

    app.state.ai_service = AIReasoningService()
    app.state.recommender_engine = SignalRecommenderEngine()
    app.state.backtest_service = BacktestService(app.state.recommender_engine)
    app.state.vnstock_service = VnstockDataIngestionService(store=app.state.store, default_source=current_settings.provider)
    app.state.feature_store = FeatureStoreService(store=app.state.store)

    app.state.latest_recommendation = None
    app.state.latest_insight = None
    app.state.recommendation_feed = deque(maxlen=50)
    app.state.history_sync_status = {}
    app.state.recommendation_replay_jobs = {}

    app.state.feed = RealtimeMarketFeed(
        app=app,
        websocket_manager=manager,
        symbols=[current_settings.symbol],
        poll_interval_sec=settings.realtime_poll_interval,
    )
    await app.state.feed.sync_with_market()
    app.state.feed.start()

    app.state.history_task = asyncio.create_task(run_history_sync_loop(app))
    app.state.insight_task = asyncio.create_task(run_ai_insight_loop(app))
    app.state.recommender_task = asyncio.create_task(run_recommendation_loop(app))

    try:
        await app.state.notifier.send_alert("VN AI Signal Lab started", level="SYSTEM")
    except Exception:
        pass

    logger.info("VN AI Signal Lab is ready")
    yield

    logger.info("Shutting down VN AI Signal Lab...")
    try:
        await app.state.notifier.send_alert("VN AI Signal Lab shutting down", level="SYSTEM")
    except Exception:
        pass

    app.state.feed.stop()
    for task_name in ("history_task", "insight_task", "recommender_task"):
        task = getattr(app.state, task_name, None)
        if task:
            task.cancel()
    for task in getattr(app.state, "recommendation_replay_jobs", {}).values():
        task.cancel()

    if app.state.redis:
        await app.state.redis.aclose()


app = FastAPI(
    title="VN AI Signal Lab API",
    description="Signal-only AI trading backend for Vietnamese markets",
    version="0.3.0",
    docs_url="/docs",
    lifespan=lifespan,
)

app.include_router(monitor_router)
app.include_router(market_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Root"])
async def root() -> dict:
    return {
        "message": "Hello from VN AI Signal Lab",
        "version": "0.3.0",
        "mode": "signal_only",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health", tags=["Root"])
async def health() -> dict:
    redis_status = "connected" if app.state.redis else "disconnected"
    return {
        "status": "ok",
        "redis": redis_status,
        "mode": "signal_only",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await websocket.send_json({"type": "CONNECTION", "message": "Connected"})
        while True:
            await asyncio.sleep(5)
            await websocket.send_json(
                {"type": "HEARTBEAT", "timestamp": datetime.now(timezone.utc).isoformat()}
            )
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
