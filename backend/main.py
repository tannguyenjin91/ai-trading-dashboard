# backend/main.py
# FastAPI application entry point for vn-ai-trader.
# Modularized Architecture: Strategy Signal Layer + Broker Execution Layer.

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import redis.asyncio as aioredis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config.logging import setup_logging
from config.settings import settings
from data.feed import AsyncMockFeed
from data.cache import get_recent_ticks, aggregate_to_ohlcv
from data.store import DiskDataStore

# New Architecture Imports
from strategy_signal.ai_reasoner import AIReasoningService
from strategy_signal.signal_service import SignalService
from strategy_signal.recommender import SignalRecommenderEngine
from agent.prompt import RECOMMENDATION_SYSTEM_PROMPT, build_recommendation_prompt
from execution.tcbs_connector import TcbsBrokerAdapter
from execution.risk_engine import RiskEngine
from execution.execution_service import ExecutionService
from monitoring.audit_log import AuditLogger
from monitoring.telegram_bot import TelegramNotifier
from monitoring.system_monitor import SystemMonitor
from api.monitor import router as monitor_router

# Hybrid Data & Execution Imports
from data.market_cache import LiveMarketCache
from strategy_signal.refinement_service import LiveSignalRefinementService
from execution.reconciliation_service import OrderReconciliationService
from data.vnstock_service import VnstockDataIngestionService
from data.feature_store import FeatureStoreService
from data.dnse_service import DnseDataIngestionService
from strategy_signal.research_engine import ResearchEngineService

class ConnectionManager:
    """Manages active WebSocket connections for broadcasting market updates."""
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected — total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected — total: {len(self.active_connections)}")

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

async def run_analysis_loop(app: FastAPI):
    """
    Periodically fetches ticks from cache, generates signals, and executes trades.
    Orchestrated via SignalService and ExecutionService.
    """
    while True:
        await asyncio.sleep(10)
        
        # Check Kill Switch status
        if hasattr(app.state, "monitor") and app.state.monitor.is_kill_switch_active:
            logger.warning("🚫 Analysis loop paused: Kill Switch is ACTIVE")
            continue
            
        try:
            symbol = "VN30F1M" 
            ticks = await get_recent_ticks(app.state.redis, symbol, limit=5000)
            if not ticks:
                continue
            
            # 1. Aggregate into candles
            df = aggregate_to_ohlcv(ticks, timeframe="2s") 
            if len(df) < 20:
                logger.debug(f"⏳ Accumulating data... ({len(df)}/20 candles)")
                continue

            # 2. Persist candle (Persistence Layer)
            if hasattr(app.state, "store"):
                await app.state.store.save_candle(
                    symbol=symbol,
                    timestamp=df.index[-1],
                    ohlcv=df.iloc[-1].to_dict(),
                    timeframe="2s"
                )

            # 3. Strategy Signal Block
            # SignalService coordinates: Features -> Signals -> AI Reasoning -> TradeIntent
            active_pos_count = len(await app.state.broker_adapter.get_positions())
            intent = await app.state.signal_service.generate_trade_intent(
                symbol=symbol,
                df=df,
                active_positions_count=active_pos_count
            )
            
            if intent:
                # Log Cycle & Intent
                if hasattr(app.state, "audit"):
                    await app.state.audit.log_cycle({"symbol": symbol, "time": datetime.now().isoformat()})
                    await app.state.audit.log_decision(intent.model_dump())

                # Broadcast Intent to Frontend
                await manager.broadcast({"type": "SIGNAL", "data": intent.model_dump()})
                
                # Wire Telegram Notification
                if hasattr(app.state, "notifier") and app.state.notifier:
                    asyncio.create_task(app.state.notifier.send_trade_signal(intent))
                
                # 4. Broker Execution Block
                # ExecutionService coordinates: Intent -> Risk Gate -> Broker Adapter -> Notifications
                # Pass the timestamp of the last candle for staleness check
                last_candle_time = df.index[-1]
                if hasattr(last_candle_time, 'to_pydatetime'):
                    last_candle_time = last_candle_time.to_pydatetime()
                
                receipt = await app.state.execution_service.execute_intent(
                    intent=intent, 
                    last_candle_time=last_candle_time
                )
                
                if receipt:
                    # Broadcast Execution Update
                    await manager.broadcast({"type": "EXECUTION", "data": receipt.model_dump()})

            # 5. Broadcast System Status Update
            if hasattr(app.state, "monitor"):
                await manager.broadcast({
                    "type": "SYSTEM_STATUS", 
                    "data": app.state.monitor.get_status_summary()
                })
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Analysis loop critical error: {e}")

async def run_ai_insight_loop(app: FastAPI):
    """Periodically queries LLM for general market framework to display on dashboard."""
    await asyncio.sleep(15) # Wait 15s on startup to let data feed populate
    while True:
        try:
            if not hasattr(app.state, "ai_service") or not app.state.ai_service:
                await asyncio.sleep(900)
                continue
            
            symbol = "VN30F1M"
            ticks = await get_recent_ticks(app.state.redis, symbol, limit=5000)
            if not ticks:
                await asyncio.sleep(60) # retry sooner if no data
                continue
                
            df = aggregate_to_ohlcv(ticks, timeframe="1m")
            if len(df) < 20: 
                await asyncio.sleep(60) # retry sooner if not enough data
                continue
                
            insight = await app.state.ai_service.generate_market_insight(df)
            if insight:
                await manager.broadcast({
                    "type": "AI_INSIGHT",
                    "data": insight
                })
                
                # Send Telegram notification with rich summary
                if hasattr(app.state, "notifier") and app.state.notifier:
                    bias = insight.get("bias", "NEUTRAL")
                    bias_emoji = "🟢" if bias == "BULLISH" else ("🔴" if bias == "BEARISH" else "⚪")
                    one_liner = insight.get("one_liner", "")
                    supports = insight.get("supports", [])
                    resistances = insight.get("resistances", [])
                    nearest_fib = insight.get("nearest_fib_zone", "N/A")
                    scenario_bull = insight.get("scenario_bullish", "")
                    scenario_bear = insight.get("scenario_bearish", "")
                    risk_note = insight.get("risk_note", "")
                    confidence = insight.get("confidence", 0)
                    price = insight.get("current_price", 0)
                    change_pct = insight.get("price_change_pct", 0)
                    regime = insight.get("regime", "UNKNOWN")
                    
                    s_str = " / ".join(f"{s:,.0f}" for s in supports[:2]) if supports else "N/A"
                    r_str = " / ".join(f"{r:,.0f}" for r in resistances[:2]) if resistances else "N/A"
                    
                    tg_message = (
                        f"{bias_emoji} <b>AI Market Insight — VN30F1M</b>\n\n"
                        f"<b>{one_liner}</b>\n\n"
                        f"📊 Giá: <code>{price:,.1f}</code> ({change_pct:+.2f}%) | Regime: {regime}\n"
                        f"🛡 Hỗ trợ: {s_str}\n"
                        f"⚡ Kháng cự: {r_str}\n"
                        f"🔢 Fib gần nhất: {nearest_fib}\n\n"
                        f"📈 Bull: {scenario_bull}\n"
                        f"📉 Bear: {scenario_bear}\n\n"
                        f"⚠️ {risk_note}\n"
                        f"<i>Confidence: {confidence}%</i>"
                    )
                    asyncio.create_task(app.state.notifier.send_message(tg_message))

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"AI insight loop error: {e}")
            
        await asyncio.sleep(900) # Run every 15m

async def run_recommendation_loop(app: FastAPI):
    """Periodically runs the deterministic rule-based signal recommendation engine."""
    await asyncio.sleep(10) # Initial wait
    while True:
        try:
            if not hasattr(app.state, "recommender_engine") or not app.state.recommender_engine:
                await asyncio.sleep(60)
                continue
                
            symbol = "VN30F1M"
            ticks = await get_recent_ticks(app.state.redis, symbol, limit=5000)
            if not ticks:
                await asyncio.sleep(60)
                continue
                
            df = aggregate_to_ohlcv(ticks, timeframe="1m")
            if len(df) < 50:
                await asyncio.sleep(60)
                continue
            
            # 1. Generate Technical-First Signal
            rec = app.state.recommender_engine.generate_recommendation(df, symbol)
            
            # Process recommendation unconditionally every 15 mins
            if rec and app.state.ai_service:
                # 2. Add AI Narrative Layer
                from indicators.engine import build_features
                features_df = build_features(df)
                latest_candle = features_df.iloc[-1].to_dict()
                
                try:
                    user_prompt = build_recommendation_prompt(rec.model_dump(), latest_candle)
                    ai_dict = await app.state.ai_service.llm.analyze_market(RECOMMENDATION_SYSTEM_PROMPT, user_prompt)
                    
                    if ai_dict:
                        # Keep technical recommendations intact, only update explanations
                        raw_reasoning = ai_dict.get("reasoning")
                        if isinstance(raw_reasoning, list) and len(raw_reasoning) > 0:
                            rec.reasoning = raw_reasoning
                        elif isinstance(raw_reasoning, str):
                            rec.reasoning = [raw_reasoning]
                            
                        rec.risk_note = ai_dict.get("risk_note", "")
                except Exception as e:
                    logger.error(f"Failed to get AI narrative for recommendation: {e}")
            
                # 3. Broadcast to Dashboard
                await manager.broadcast({
                    "type": "RECOMMENDATION",
                    "data": rec.model_dump()
                })
                
                # 4. Telegram Alert
                if hasattr(app.state, "notifier") and app.state.notifier:
                    # Format rich text
                    emoji = "🟢" if rec.recommendation == "BUY" else ("🔴" if rec.recommendation == "SELL" else "⚪")
                    entry_str = f"{rec.entry_zone.min_price:,.1f} - {rec.entry_zone.max_price:,.1f}" if rec.entry_zone else "N/A"
                    targets_str = ", ".join([f"{t:,.1f}" for t in rec.take_profit_targets]) if rec.take_profit_targets else "N/A"
                    stop_str = f"{rec.stop_loss:,.1f}" if rec.stop_loss else "N/A"
                    reason_str = "\n".join(rec.reasoning) if rec.reasoning else "Nội bộ Engine quyết định."
                    
                    msg = (
                        f"{emoji} <b>[TÍN HIỆU] {rec.recommendation} {rec.symbol}</b>\n\n"
                        f"📊 <b>Giá hiện tại:</b> <code>{rec.current_price:,.1f}</code>\n"
                        f"🎯 <b>Vùng Mua/Bán:</b> {entry_str}\n"
                        f"🛡 <b>Stop Loss:</b> {stop_str}\n"
                        f"🚀 <b>Take Profit:</b> {targets_str}\n"
                        f"📈 <b>Confidence:</b> {rec.confidence}%\n\n"
                        f"💬 <b>Phân tích:</b> {reason_str}\n\n"
                        f"⚠️ <i>Rủi ro: {rec.risk_note}</i>\n"
                    )
                    asyncio.create_task(app.state.notifier.send_message(msg))
                    
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Recommendation loop error: {e}")
            
        await asyncio.sleep(900) # Run every 15 minutes

async def run_reconciliation_loop(app: FastAPI):
    """Periodically triggers position reconciliation to fix stale or zombie orders."""
    while True:
        await asyncio.sleep(45) # Run every 45s
        try:
            if not hasattr(app.state, "reconciler") or not hasattr(app.state, "broker_adapter"):
                continue
                
            portfolio = await app.state.broker_adapter.get_portfolio()
            positions = await app.state.broker_adapter.get_positions()
            
            await app.state.reconciler.reconcile_positions(
                broker_portfolio=portfolio,
                active_positions=positions
            )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Reconciliation loop error: {e}")

# ── Startup / Shutdown lifespan ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    logger.info("Starting VN AI Trader backend...")
    logger.info(f"Environment: {settings.environment.value} | Paper Mode: {settings.tcbs_paper_mode} | Live Trading: {settings.live_trading}")

    # 1. Infrastructure Setup
    try:
        app.state.redis = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        await app.state.redis.ping()
        logger.info(f"✅ Redis connected")
    except Exception as e:
        logger.warning(f"⚠️ Redis unavailable: {e}")
        app.state.redis = None

    app.state.store = DiskDataStore(db_path="market_data.db")
    await app.state.store.init_db()

    app.state.audit = AuditLogger(settings.database_url)
    await app.state.audit.init_db()
    
    app.state.notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token.get_secret_value() if settings.telegram_bot_token else "",
        chat_id=settings.telegram_chat_id.get_secret_value() if settings.telegram_chat_id else ""
    )
    
    # 2. Monitoring & Safety
    app.state.monitor = SystemMonitor(settings)
    app.state.telegram = app.state.notifier # Alias if needed, but updated to use app.state.notifier

    # 2. Strategy Signal Layer Setup
    app.state.ai_service = AIReasoningService()
    app.state.signal_service = SignalService(ai_service=app.state.ai_service)
    app.state.recommender_engine = SignalRecommenderEngine()

    # 0. Hybrid Data Layer (Pipeline 2 Live Cache)
    app.state.market_cache = LiveMarketCache(stale_threshold_sec=2.0)
    app.state.refinement_service = LiveSignalRefinementService(cache=app.state.market_cache)
    app.state.reconciler = OrderReconciliationService(notifier=app.state.telegram)

    # 0.1 Pipeline 1 (Research Data) - DNSE Preferred
    app.state.vnstock_service = VnstockDataIngestionService(store=app.state.store)
    app.state.dnse_service = DnseDataIngestionService(
        store=app.state.store,
        api_key=settings.dnse_api_key.get_secret_value()
    )
    app.state.feature_store = FeatureStoreService(store=app.state.store)
    app.state.research_engine = ResearchEngineService(
        store=app.state.store, 
        feature_store=app.state.feature_store
    )

    # 3. Broker Execution Layer Setup
    app.state.broker_adapter = TcbsBrokerAdapter(
        username=settings.tcbs_username,
        password=settings.tcbs_password,
        totp_secret=settings.tcbs_totp_secret.get_secret_value() if settings.tcbs_totp_secret else "",
        paper_mode=settings.tcbs_paper_mode,
        monitor=app.state.monitor
    )
    app.state.risk_engine = RiskEngine(settings=settings)
    app.state.execution_service = ExecutionService(
        broker=app.state.broker_adapter,
        risk_engine=app.state.risk_engine,
        refinement_service=app.state.refinement_service, # Injected
        notifier=app.state.telegram,
        audit_logger=app.state.audit
    )
    app.state.execution_service.monitor = app.state.monitor # Attach monitor

    # 4. Data Feed & Background Tasks
    app.state.feed = AsyncMockFeed(app, manager, interval_sec=0.5)
    app.state.feed.start()
    
    # 5. Background Strategy Loops
    app.state.analyzer_task = asyncio.create_task(run_analysis_loop(app))
    app.state.insight_task = asyncio.create_task(run_ai_insight_loop(app))
    app.state.recommender_task = asyncio.create_task(run_recommendation_loop(app))
    app.state.reconciler_task = asyncio.create_task(run_reconciliation_loop(app))
    
    # TCBS Market Data Stream (Optional: depending on if we want live data now)
    # app.state.broker_stream_task = asyncio.create_task(
    #     app.state.broker_adapter.stream_market_data(["VN30F2406"], some_callback)
    # )

    await app.state.telegram.send_alert("VN AI Trader System Started", level="SYSTEM")
    logger.info("VN AI Trader is ready")
    yield

    # Shutdown
    logger.info("Shutting down VN AI Trader...")
    await app.state.telegram.send_alert("VN AI Trader System Shutting Down", level="SYSTEM")
    app.state.feed.stop()
    if app.state.analyzer_task:
        app.state.analyzer_task.cancel()
    if getattr(app.state, "insight_task", None):
        app.state.insight_task.cancel()
    if getattr(app.state, "recommender_task", None):
        app.state.recommender_task.cancel()
    if getattr(app.state, "reconciler_task", None):
        app.state.reconciler_task.cancel()
    if app.state.redis:
        await app.state.redis.aclose()


# ── FastAPI App ──────────────────────────────────────────────────────────────
from api.monitor import router as monitor_router
from api.market_api import router as market_router

app = FastAPI(
    title="VN AI Trader API",
    description="Autonomous AI trading backend for Vietnamese stock markets",
    version="0.2.0",
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
        "message": "Hello from VN AI Trader",
        "version": "0.2.0",
        "architecture": "Modularized Strategy+Execution",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/health", tags=["Root"])
async def health() -> dict:
    redis_status = "connected" if app.state.redis else "disconnected"
    return {
        "status": "ok",
        "redis": redis_status,
        "paper_mode": settings.tcbs_paper_mode,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await websocket.send_json({"type": "CONNECTION", "message": "Connected"})
        while True:
            await asyncio.sleep(5)
            await websocket.send_json({"type": "HEARTBEAT", "timestamp": datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)
