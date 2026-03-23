# backend/data/feed.py
# Simulates a live WebSocket market data feed for testing and paper trading.

import asyncio
import random
from datetime import datetime, timezone
from loguru import logger

from data.normalizer import TickData
from data.cache import save_tick

from enum import Enum

class MarketRegime(Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    SIDEWAYS = "sideways"
    VOLATILE = "volatile"

# Baseline pseudo-prices for mock symbols
_BASE_PRICES = {
    "VN30F1M": 1250.5,
    "HPG": 27.50,
    "SSI": 35.20
}

class AsyncMockFeed:
    """
    Runs an asynchronous background loop generating fake trades.
    Supports regimes to simulate specific market conditions.
    """
    def __init__(self, app, websocket_manager, interval_sec: float = 1.0, regime: MarketRegime = MarketRegime.SIDEWAYS):
        self.app = app
        self.manager = websocket_manager
        self.interval = interval_sec
        self.regime = regime
        self.is_running = False
        self._task = None
        self.prices = _BASE_PRICES.copy()

    def start(self):
        """Starts the mock feed task."""
        self.is_running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"Mock Feed started with {self.interval}s interval.")

    def stop(self):
        """Stops the mock feed task."""
        self.is_running = False
        if self._task:
            self._task.cancel()
        logger.info("Mock Feed stopped.")

    async def _loop(self):
        while self.is_running:
            try:
                for symbol in self.prices.keys():
                    # Base volatility (0.05% per tick)
                    vol_factor = 0.0005
                    
                    if self.regime == MarketRegime.TRENDING_UP:
                        drift = 0.0002 # 0.02% drift up
                        noise = random.uniform(-vol_factor, vol_factor * 1.5)
                    elif self.regime == MarketRegime.TRENDING_DOWN:
                        drift = -0.0002 # 0.02% drift down
                        noise = random.uniform(-vol_factor * 1.5, vol_factor)
                    elif self.regime == MarketRegime.VOLATILE:
                        drift = 0
                        noise = random.uniform(-vol_factor * 3, vol_factor * 3)
                    else: # SIDEWAYS
                        drift = 0
                        noise = random.uniform(-vol_factor, vol_factor)
                    
                    change_pct = drift + noise
                    self.prices[symbol] *= (1 + change_pct)
                    
                    # Ensure strictly positive
                    self.prices[symbol] = max(1.0, self.prices[symbol])
                    
                    tick = TickData(
                        symbol=symbol,
                        price=round(self.prices[symbol], 2),
                        volume=random.randint(1, 100),
                        timestamp=datetime.now(timezone.utc),
                        is_buyer_maker=random.choice([True, False])
                    )
                    
                    # 1. Save to Cache/Redis
                    await save_tick(self.app.state.redis, symbol, tick)
                    
                    # 2. Update Position Monitor (Phase 4)
                    if hasattr(self.app.state, "monitor"):
                        await self.app.state.monitor.update_tick(symbol, self.prices[symbol])
                    
                    # 3. Update Live Market Cache (Hybrid Architecture)
                    if hasattr(self.app.state, "market_cache"):
                        self.app.state.market_cache.update_snapshot(
                            symbol=symbol,
                            price=self.prices[symbol],
                            timestamp=datetime.now()
                        )

                    # 4. Broadcast to connected WebSocket clients (Frontend)
                    await self.manager.broadcast({
                        "type": "TICK",
                        "data": tick.model_dump(mode="json")
                    })
                    
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Mock feed error: {e}")
                await asyncio.sleep(self.interval)
