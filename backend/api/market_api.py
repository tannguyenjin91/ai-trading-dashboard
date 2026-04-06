from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from shared.models import SignalRecommendation
from strategy_signal.strategy_settings import StrategySettings

router = APIRouter(prefix="/v1/market", tags=["Market Data"])


class MarketOverviewResponse(BaseModel):
    symbol: str
    price: float
    change_pct: float
    volume: int
    last_updated: float
    source: str


class RecommendationFeedResponse(BaseModel):
    items: List[SignalRecommendation]
    latest: Optional[SignalRecommendation] = None
    count: int


class StrategySettingsUpdateRequest(BaseModel):
    symbol: Optional[str] = None
    provider: Optional[str] = None
    analysis_interval_sec: Optional[int] = Field(default=None, ge=60, le=3600)
    history_window_days: Optional[int] = Field(default=None, ge=5, le=120)
    history_sync_interval_sec: Optional[int] = Field(default=None, ge=300, le=86400)
    ai_enabled: Optional[bool] = None
    ai_model: Optional[str] = None
    min_confidence: Optional[float] = Field(default=None, ge=0, le=100)
    risk_per_trade_pct: Optional[float] = Field(default=None, ge=0.1, le=5)
    initial_capital: Optional[float] = Field(default=None, gt=0)
    max_open_positions: Optional[int] = Field(default=None, ge=1, le=10)
    slippage_bps: Optional[float] = Field(default=None, ge=0)
    fee_bps: Optional[float] = Field(default=None, ge=0)
    allow_short: Optional[bool] = None
    auto_journal_signals: Optional[bool] = None
    notes: Optional[str] = None


class BacktestRequest(BaseModel):
    symbol: Optional[str] = None
    provider: Optional[str] = None
    strategy: str = "mtf_signal"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: Optional[float] = Field(default=None, gt=0)
    min_confidence: Optional[float] = Field(default=None, ge=0, le=100)
    risk_per_trade_pct: Optional[float] = Field(default=None, ge=0.1, le=5)
    allow_short: Optional[bool] = None


class RecommendationReplayRequest(BaseModel):
    symbol: Optional[str] = None
    provider: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    include_ai: bool = True


@router.get("/overview", response_model=MarketOverviewResponse)
async def get_market_overview(request: Request, symbol: str | None = None):
    settings = await request.app.state.strategy_settings.get_settings()
    selected_symbol = (symbol or settings.symbol).upper()

    snapshot = None
    cache = getattr(request.app.state, "market_cache", None)
    if cache:
        snapshot = cache.get_snapshot_dict(selected_symbol)

    price = 0.0
    volume = 0
    source = "vnstock"
    last_updated = datetime.now().timestamp()

    if snapshot and snapshot.get("price"):
        price = float(snapshot["price"])
        volume = int(snapshot.get("volume") or 0)
        source = snapshot.get("source", "live_cache")
        if snapshot.get("timestamp"):
            try:
                last_updated = datetime.fromisoformat(snapshot["timestamp"]).timestamp()
            except ValueError:
                pass

    daily_bars = await request.app.state.vnstock_service.fetch_history(
        selected_symbol,
        timeframe="1D",
        limit=2,
        source=settings.provider,
    )
    if not daily_bars and price <= 0:
        return MarketOverviewResponse(
            symbol=selected_symbol,
            price=0,
            change_pct=0,
            volume=0,
            last_updated=0,
            source="unavailable",
        )

    current_bar = daily_bars[-1] if daily_bars else None
    if current_bar and price <= 0:
        price = current_bar.close
        volume = current_bar.volume
        last_updated = current_bar.timestamp.timestamp()

    change_pct = 0.0
    if len(daily_bars) >= 2 and daily_bars[-2].close > 0:
        previous_close = daily_bars[-2].close
        reference_price = price or daily_bars[-1].close
        change_pct = ((reference_price - previous_close) / previous_close) * 100

    return MarketOverviewResponse(
        symbol=selected_symbol,
        price=price,
        change_pct=change_pct,
        volume=volume,
        last_updated=last_updated,
        source=source,
    )


@router.get("/snapshot")
async def get_market_snapshot(request: Request, symbol: str = "VN30F1M"):
    cache = getattr(request.app.state, "market_cache", None)
    if not cache:
        return {"error": "Market cache not initialized", "symbol": symbol}

    snapshot = cache.get_snapshot_dict(symbol)
    if not snapshot:
        return {"symbol": symbol, "price": 0, "status": "no_data"}

    feed = getattr(request.app.state, "feed", None)
    feed_status = feed.get_status() if feed and hasattr(feed, "get_status") else {}
    return {**snapshot, "feed_status": feed_status}


@router.get("/feed-status")
async def get_feed_status(request: Request):
    feed = getattr(request.app.state, "feed", None)
    if not feed or not hasattr(feed, "get_status"):
        return {"error": "Feed not initialized"}
    return feed.get_status()


@router.get("/data-coverage")
async def get_data_coverage(request: Request, symbol: str | None = None):
    settings = await request.app.state.strategy_settings.get_settings()
    selected_symbol = (symbol or settings.symbol).upper()
    timeframes = ("1m", "5m", "15m", "1D")
    items = []
    for timeframe in timeframes:
        items.append(await request.app.state.store.get_coverage(selected_symbol, timeframe))
    return {
        "symbol": selected_symbol,
        "history_window_days": settings.history_window_days,
        "last_sync": getattr(request.app.state, "history_sync_status", {}),
        "items": items,
    }


@router.get("/recommendations", response_model=RecommendationFeedResponse)
async def get_recommendations(request: Request, limit: int = 20):
    safe_limit = max(1, min(limit, 50))
    feed = list(getattr(request.app.state, "recommendation_feed", []))
    latest = getattr(request.app.state, "latest_recommendation", None)
    items = feed[:safe_limit]
    return RecommendationFeedResponse(items=items, latest=latest, count=len(items))


@router.get("/recommendation-history")
async def get_recommendation_history(request: Request, limit: int = 100, run_id: int | None = None):
    safe_limit = max(1, min(limit, 300))
    return await request.app.state.recommendation_history.get_history(limit=safe_limit, run_id=run_id)


@router.post("/recommendation-history/replay")
async def run_recommendation_replay(request: Request, payload: RecommendationReplayRequest):
    settings = await request.app.state.strategy_settings.get_settings()
    symbol = (payload.symbol or settings.symbol).upper()
    provider = payload.provider or settings.provider
    end_date = payload.end_date or datetime.now().strftime("%Y-%m-%d")
    start_date = payload.start_date or (datetime.now() - timedelta(days=settings.history_window_days)).strftime("%Y-%m-%d")

    running_run = await request.app.state.recommendation_history.has_running_run(symbol=symbol)
    if running_run:
        return {
            "status": "already_running",
            "run_id": running_run["id"],
            "message": f"Recommendation replay is already running for {symbol}.",
        }

    run_id = await request.app.state.recommendation_history.create_run(
        symbol=symbol,
        provider=provider,
        start_date=start_date,
        end_date=end_date,
        include_ai=payload.include_ai,
    )

    async def _background_replay() -> None:
        try:
            df_1m = await request.app.state.vnstock_service.fetch_history_df(
                symbol=symbol,
                timeframe="1m",
                start=start_date,
                end=end_date,
                limit=0,
                source=provider,
            )
            if df_1m.empty:
                await request.app.state.recommendation_history._complete_run(run_id, 0, "failed")
                return

            await request.app.state.recommendation_history.execute_replay(
                run_id=run_id,
                symbol=symbol,
                provider=provider,
                start_date=start_date,
                end_date=end_date,
                settings=settings,
                recommender=request.app.state.recommender_engine,
                ai_service=request.app.state.ai_service,
                df_1m=df_1m,
                include_ai=payload.include_ai,
            )
        finally:
            request.app.state.recommendation_replay_jobs.pop(run_id, None)

    task = asyncio.create_task(_background_replay())
    request.app.state.recommendation_replay_jobs[run_id] = task

    return {
        "status": "queued",
        "run_id": run_id,
        "symbol": symbol,
        "provider": provider,
        "start_date": start_date,
        "end_date": end_date,
        "include_ai": payload.include_ai,
        "message": "Recommendation replay started in background.",
    }


@router.get("/strategy-settings", response_model=StrategySettings)
async def get_strategy_settings(request: Request):
    return await request.app.state.strategy_settings.get_settings()


@router.put("/strategy-settings", response_model=StrategySettings)
async def update_strategy_settings(request: Request, payload: StrategySettingsUpdateRequest):
    patch = payload.model_dump(exclude_none=True)
    if not patch:
        return await request.app.state.strategy_settings.get_settings()
    if "provider" in patch:
        patch["provider"] = str(patch["provider"]).upper()
    if "symbol" in patch:
        patch["symbol"] = str(patch["symbol"]).upper()
    return await request.app.state.strategy_settings.update_settings(patch)


@router.get("/portfolio")
async def get_portfolio_summary(request: Request, limit: int = 20, days: int = 30):
    settings = await request.app.state.strategy_settings.get_settings()
    return await request.app.state.signal_journal.get_portfolio_summary(settings, limit=limit, days=days)


@router.get("/order-history")
async def get_order_history(request: Request, limit: int = 50, days: int = 30):
    safe_limit = max(1, min(limit, 200))
    safe_days = max(1, min(days, 90))
    return await request.app.state.signal_journal.get_order_history(limit=safe_limit, days=safe_days)


@router.get("/backtest-strategies")
async def get_backtest_strategies(request: Request):
    return {
        "items": [
            {
                "id": "mtf_signal",
                "name": "MTF Signal Engine",
                "description": "Uses the existing multi-timeframe recommender and confidence gating.",
            },
            {
                "id": "ema_cross",
                "name": "EMA Cross",
                "description": "Reacts to 15m EMA9/EMA21 crossovers with ATR-based stops.",
            },
            {
                "id": "breakout_retest",
                "name": "Breakout Retest",
                "description": "Trades 15m range breaks with simple breakout risk framing.",
            },
        ]
    }


@router.post("/backtest")
async def run_backtest(request: Request, payload: BacktestRequest):
    settings = await request.app.state.strategy_settings.get_settings()
    effective_settings = settings.model_copy(
        update={
            key: value
            for key, value in payload.model_dump(exclude_none=True).items()
            if key in {
                "symbol",
                "provider",
                "initial_capital",
                "risk_per_trade_pct",
                "allow_short",
            }
        }
    )

    symbol = (payload.symbol or effective_settings.symbol).upper()
    provider = payload.provider or effective_settings.provider
    end_date = payload.end_date or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    start_date = payload.start_date or (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")

    df_1m = await request.app.state.vnstock_service.fetch_history_df(
        symbol=symbol,
        timeframe="1m",
        start=start_date,
        end=end_date,
        limit=0,
        source=provider,
    )
    if df_1m.empty:
        raise HTTPException(status_code=400, detail="No vnstock data available for the selected period.")

    result = request.app.state.backtest_service.run(
        symbol=symbol,
        df_1m=df_1m,
        settings=effective_settings,
        min_confidence=payload.min_confidence,
        strategy_name=payload.strategy,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/audit-log")
async def get_audit_log(request: Request, limit: int = 20):
    safe_limit = max(1, min(limit, 100))
    return {"items": await request.app.state.audit.query_recent(limit=safe_limit)}
