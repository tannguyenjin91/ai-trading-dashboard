# backend/data/realtime_feed.py
# Realtime market data feed using DNSE LightSpeed WebSocket (MQTT) as primary source
# with REST polling fallback. Replaces AsyncMockFeed for production use.

import asyncio
import json
import random
import time
import uuid
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Dict, Any, Callable

import aiohttp
from loguru import logger

from data.normalizer import TickData
from data.cache import save_tick
from config.settings import settings


def is_vn_market_open() -> bool:
    """Checks if current time is within Vietnam trading hours (Mon-Fri, 08:45-15:00, excluding lunch 11:30-13:00)."""
    vn_tz = timezone(timedelta(hours=7))
    now = datetime.now(vn_tz)
    
    # Weekends Check (0 = Monday, 6 = Sunday)
    if now.weekday() >= 5:
        return False
        
    current_time = now.time()
    
    # Morning session
    morning_start = now.replace(hour=8, minute=45, second=0, microsecond=0).time()
    morning_end = now.replace(hour=11, minute=30, second=0, microsecond=0).time()
    
    # Afternoon session
    afternoon_start = now.replace(hour=13, minute=0, second=0, microsecond=0).time()
    afternoon_end = now.replace(hour=15, minute=0, second=0, microsecond=0).time()
    
    is_morning = morning_start <= current_time <= morning_end
    is_afternoon = afternoon_start <= current_time <= afternoon_end
    
    return is_morning or is_afternoon


class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    CONNECTING = "connecting"


class FeedSource(str, Enum):
    DNSE_WS = "dnse_websocket"
    DNSE_REST = "dnse_rest"
    MOCK = "mock"


class RealtimeMarketFeed:
    """
    Realtime market data feed with three-tier fallback:
      1. DNSE LightSpeed WebSocket (MQTT over WSS) — sub-second updates
      2. DNSE REST API polling — configurable interval (default 5s)
      3. Mock data — for development when DNSE is unreachable

    Broadcasts TICK and MARKET_STATUS messages via the existing WebSocket manager.
    """

    # DNSE LightSpeed endpoints
    DNSE_WS_URL = "wss://datafeed-lts-krx.dnse.com.vn:443/wss"
    DNSE_AUTH_URL = "https://api.dnse.com.vn/user-service/api/auth"
    DNSE_ME_URL = "https://api.dnse.com.vn/user-service/api/me"
    DNSE_REST_URL = "https://services.entrade.com.vn/chart-api/v2/ohlcs"

    def __init__(
        self,
        app,
        websocket_manager,
        symbols: list[str] = None,
        poll_interval_sec: float = 5.0,
    ):
        self.app = app
        self.manager = websocket_manager
        self.symbols = symbols or ["VN30F1M"]
        self.poll_interval = poll_interval_sec

        # State
        self.is_running = False
        self._ws_task: Optional[asyncio.Task] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._status_task: Optional[asyncio.Task] = None
        self._ws_session: Optional[aiohttp.ClientSession] = None
        self._ws_connection: Optional[aiohttp.ClientWebSocketResponse] = None

        # Connection tracking
        self.connection_status = ConnectionStatus.DISCONNECTED
        self.active_source = FeedSource.MOCK
        self.last_tick_at: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.reconnect_count = 0
        self._stale_threshold_sec = settings.stale_data_threshold_sec or 30

        # DNSE auth
        self._jwt_token: Optional[str] = None
        self._investor_id: Optional[str] = None
        self._jwt_expires_at: float = 0

        # Price state for mock fallback
        self._mock_prices: Dict[str, float] = {"VN30F1M": 1760.0, "HPG": 27.50, "SSI": 35.20}

        # Track last known prices for change calculation
        self._last_prices: Dict[str, float] = {}
        self._session_high: Dict[str, float] = {}
        self._session_low: Dict[str, float] = {}
        self._session_volume: Dict[str, int] = {}

    # ── Public API (same interface as AsyncMockFeed) ──────────────────────────

    def start(self):
        """Starts the realtime feed."""
        self.is_running = True
        self.connection_status = ConnectionStatus.CONNECTING

        # Try WebSocket first, fall back to polling
        self._ws_task = asyncio.create_task(self._ws_loop())
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._status_task = asyncio.create_task(self._status_broadcast_loop())

        logger.info(f"RealtimeMarketFeed started — symbols: {self.symbols}, poll_interval: {self.poll_interval}s")

    def stop(self):
        """Stops the realtime feed."""
        self.is_running = False
        self.connection_status = ConnectionStatus.DISCONNECTED
        for task in [self._ws_task, self._poll_task, self._status_task]:
            if task:
                task.cancel()
        logger.info("RealtimeMarketFeed stopped.")

    async def sync_with_market(self, dnse_service=None):
        """Fetches initial prices from DNSE REST to initialize price state."""
        logger.info("RealtimeMarketFeed: Syncing initial prices from DNSE REST...")
        for symbol in self.symbols:
            try:
                price = await self._fetch_latest_price_rest(symbol)
                if price and price > 0:
                    self._last_prices[symbol] = price
                    self._mock_prices[symbol] = price
                    self._session_high[symbol] = price
                    self._session_low[symbol] = price
                    logger.success(f"Synced {symbol} → {price}")
            except Exception as e:
                logger.warning(f"Failed to sync {symbol}: {e}")

    def get_status(self) -> dict:
        """Returns current feed status as a serializable dict."""
        now = datetime.now(timezone.utc)
        is_stale = True
        if self.last_tick_at:
            elapsed = (now - self.last_tick_at).total_seconds()
            is_stale = elapsed > self._stale_threshold_sec

        return {
            "connection_status": self.connection_status.value,
            "source": self.active_source.value,
            "is_stale": is_stale,
            "market_session": "OPEN" if is_vn_market_open() else "CLOSED",
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "reconnect_count": self.reconnect_count,
            "last_error": self.last_error,
            "symbols": self.symbols,
            "poll_interval_sec": self.poll_interval,
        }

    # ── DNSE WebSocket (MQTT over WSS) ───────────────────────────────────────

    async def _authenticate_dnse(self) -> bool:
        """Authenticates with DNSE to get JWT token for WebSocket."""
        username = getattr(settings, 'dnse_username', '') or ''
        password = getattr(settings, 'dnse_password', '') or ''

        if not username or not password:
            logger.debug("DNSE WebSocket auth: No credentials configured, using public topics only")
            return True  # public topics don't need auth

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.DNSE_AUTH_URL,
                    json={"username": username, "password": password},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._jwt_token = data.get("token") or data.get("accessToken")
                        self._jwt_expires_at = time.time() + (7 * 3600)  # ~7h safety margin

                        # Get investor ID
                        async with session.get(
                            self.DNSE_ME_URL,
                            headers={"Authorization": f"Bearer {self._jwt_token}"},
                            timeout=aiohttp.ClientTimeout(total=10),
                        ) as me_resp:
                            if me_resp.status == 200:
                                me_data = await me_resp.json()
                                self._investor_id = str(me_data.get("investorId", ""))
                                logger.success(f"DNSE auth success — investor: {self._investor_id}")
                                return True

                    logger.warning(f"DNSE auth failed: HTTP {resp.status}")
                    return False
        except Exception as e:
            logger.warning(f"DNSE auth error: {e}")
            return False

    async def _ws_loop(self):
        """Main WebSocket connection loop with exponential backoff reconnect."""
        backoff = 1.0
        max_backoff = 60.0

        while self.is_running:
            try:
                await self._authenticate_dnse()

                self.connection_status = ConnectionStatus.CONNECTING
                self._ws_session = aiohttp.ClientSession()

                # Build MQTT-style WebSocket connection
                # For public topics, no auth header needed
                headers = {}
                ws_url = self.DNSE_WS_URL

                logger.info(f"Connecting to DNSE WebSocket: {ws_url}")

                self._ws_connection = await self._ws_session.ws_connect(
                    ws_url,
                    timeout=aiohttp.ClientTimeout(total=15),
                    heartbeat=30,
                    headers=headers,
                )

                self.connection_status = ConnectionStatus.CONNECTED
                self.active_source = FeedSource.DNSE_WS
                self.last_error = None
                backoff = 1.0  # Reset backoff on success
                logger.success("DNSE WebSocket connected!")

                # Subscribe to topics for each symbol
                for symbol in self.symbols:
                    await self._subscribe_topics(symbol)

                # Read messages
                async for msg in self._ws_connection:
                    if not self.is_running:
                        break

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_ws_message(msg.data)
                    elif msg.type == aiohttp.WSMsgType.BINARY:
                        await self._handle_ws_message(msg.data.decode("utf-8", errors="ignore"))
                    elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                        logger.warning(f"DNSE WebSocket closed: {msg.type}")
                        break

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.last_error = str(e)
                logger.warning(f"DNSE WebSocket error: {e}")
            finally:
                # Cleanup
                if self._ws_connection and not self._ws_connection.closed:
                    await self._ws_connection.close()
                if self._ws_session and not self._ws_session.closed:
                    await self._ws_session.close()
                self._ws_connection = None
                self._ws_session = None

            if not self.is_running:
                break

            # Reconnect with backoff
            self.connection_status = ConnectionStatus.RECONNECTING
            self.reconnect_count += 1
            logger.info(f"DNSE WebSocket reconnecting in {backoff:.1f}s (attempt #{self.reconnect_count})")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

    async def _subscribe_topics(self, symbol: str):
        """Subscribes to DNSE MQTT topics for a symbol."""
        if not self._ws_connection:
            return

        # Determine type
        sym_type = "derivative" if symbol.startswith("VN30F") else "stock"

        # Topic patterns from DNSE docs
        topics = [
            f"plaintext/quotes/{sym_type}/SI/{symbol}",       # Stock info
            f"plaintext/quotes/{sym_type}/TP/{symbol}",       # Top prices
        ]

        # MQTT Subscribe packet (simplified — DNSE may use plain JSON subscribe)
        for topic in topics:
            try:
                subscribe_msg = json.dumps({"action": "subscribe", "topic": topic})
                await self._ws_connection.send_str(subscribe_msg)
                logger.debug(f"Subscribed to: {topic}")
            except Exception as e:
                logger.warning(f"Failed to subscribe to {topic}: {e}")

    async def _handle_ws_message(self, raw: str):
        """Parses incoming DNSE WebSocket message and emits ticks."""
        try:
            data = json.loads(raw)

            # DNSE may send various message formats — try to extract price
            price = None
            symbol = None
            volume = 0

            # Standard stock info format
            if "lastPrice" in data:
                price = float(data["lastPrice"])
                symbol = data.get("symbol", data.get("stockSymbol", self.symbols[0]))
                volume = int(data.get("totalVolume", data.get("matchVolume", 0)))
            elif "c" in data and isinstance(data["c"], (int, float)):
                # OHLC format
                price = float(data["c"])
                symbol = data.get("s", data.get("symbol", self.symbols[0]))
                volume = int(data.get("v", 0))
            elif "matchPrice" in data:
                price = float(data["matchPrice"])
                symbol = data.get("symbol", data.get("stockSymbol", self.symbols[0]))
                volume = int(data.get("matchVolume", 0))
            elif "price" in data:
                price = float(data["price"])
                symbol = data.get("symbol", self.symbols[0])
                volume = int(data.get("volume", 0))

            if price and price > 0 and symbol:
                await self._emit_tick(symbol, price, volume, FeedSource.DNSE_WS)

        except json.JSONDecodeError:
            pass  # Binary/non-JSON messages
        except Exception as e:
            logger.debug(f"WS message parse error: {e}")

    # ── REST Polling Fallback ────────────────────────────────────────────────

    async def _poll_loop(self):
        """REST polling fallback — runs when WebSocket is not connected."""
        # Wait a bit for WS to connect first
        await asyncio.sleep(3.0)

        while self.is_running:
            try:
                # Only poll if WebSocket is NOT actively streaming
                if self.active_source == FeedSource.DNSE_WS and self.connection_status == ConnectionStatus.CONNECTED:
                    # WS is working — check for staleness
                    if self.last_tick_at:
                        elapsed = (datetime.now(timezone.utc) - self.last_tick_at).total_seconds()
                        if elapsed < self._stale_threshold_sec:
                            await asyncio.sleep(self.poll_interval)
                            continue

                # Poll REST for each symbol
                got_data = False
                for symbol in self.symbols:
                    try:
                        price = await self._fetch_latest_price_rest(symbol)
                        if price and price > 0:
                            await self._emit_tick(symbol, price, 0, FeedSource.DNSE_REST)
                            got_data = True
                    except Exception as e:
                        logger.debug(f"REST poll failed for {symbol}: {e}")

                market_open = is_vn_market_open()

                if got_data:
                    if self.active_source != FeedSource.DNSE_WS:
                        self.active_source = FeedSource.DNSE_REST
                        self.connection_status = ConnectionStatus.CONNECTED
                elif self.active_source != FeedSource.DNSE_WS:
                    # REST also failed
                    if market_open:
                        # Use mock only if market is open
                        for symbol in self.symbols:
                            await self._emit_mock_tick(symbol)
                        self.active_source = FeedSource.MOCK
                    else:
                        # Market closed, REST failed (e.g. out of window). Do NOT run mock noise.
                        if self.active_source != FeedSource.DNSE_REST:
                            self.active_source = FeedSource.DNSE_REST
                            self.connection_status = ConnectionStatus.CONNECTED

                await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Poll loop error: {e}")
                self.last_error = str(e)
                await asyncio.sleep(self.poll_interval)

    async def _fetch_latest_price_rest(self, symbol: str) -> Optional[float]:
        """Fetches the latest price from DNSE REST API (1-minute candle)."""
        endpoint = "derivative" if symbol.startswith("VN30F") else "stock"
        query_symbol = "VN30F1M" if symbol.startswith("VN30F") else symbol

        to_unix = int(datetime.now().timestamp())
        from_unix = to_unix - 86400  # Last 24h to ensure we get data even outside hours

        url = f"{self.DNSE_REST_URL}/{endpoint}"
        params = {
            "from": from_unix,
            "to": to_unix,
            "symbol": query_symbol,
            "resolution": "1",  # 1-minute
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    if resp.status != 200:
                        return None

                    data = await resp.json()

                    # Accept response if close data exists (DNSE may return s=None or s="ok")
                    closes = data.get("c", [])
                    volumes = data.get("v", [])

                    if closes:
                        price = float(closes[-1])
                        # Update volume
                        if volumes:
                            self._session_volume[symbol] = int(sum(volumes[-10:]))  # last 10 bars
                        return price

        except Exception as e:
            logger.debug(f"DNSE REST fetch error for {symbol}: {e}")
            return None

    # ── Mock Fallback ────────────────────────────────────────────────────────

    async def _emit_mock_tick(self, symbol: str):
        """Generates a mock tick when real data is unavailable."""
        base = self._mock_prices.get(symbol, 1760.0)
        noise = random.uniform(-0.0001, 0.0001)
        new_price = round(base * (1 + noise), 2)
        self._mock_prices[symbol] = new_price
        await self._emit_tick(symbol, new_price, random.randint(1, 100), FeedSource.MOCK)

    # ── Core Tick Emission ───────────────────────────────────────────────────

    async def _emit_tick(self, symbol: str, price: float, volume: int, source: FeedSource):
        """Central tick processing: saves to cache, updates state, broadcasts."""
        now = datetime.now(timezone.utc)

        # Calculate change from last known price
        prev_price = self._last_prices.get(symbol, price)
        price_change = price - prev_price
        price_change_pct = (price_change / prev_price * 100) if prev_price > 0 else 0

        # Update session tracking
        self._last_prices[symbol] = price
        if symbol not in self._session_high or price > self._session_high[symbol]:
            self._session_high[symbol] = price
        if symbol not in self._session_low or price < self._session_low[symbol]:
            self._session_low[symbol] = price

        self.last_tick_at = now

        # Build tick
        tick = TickData(
            symbol=symbol,
            price=price,
            volume=volume,
            timestamp=now,
            is_buyer_maker=random.choice([True, False]),
        )

        # 1. Save to Redis / memory cache
        if hasattr(self.app.state, "redis"):
            await save_tick(self.app.state.redis, symbol, tick)

        # 2. Update LiveMarketCache
        if hasattr(self.app.state, "market_cache"):
            self.app.state.market_cache.update_snapshot(
                symbol=symbol,
                price=price,
                volume=self._session_volume.get(symbol, volume),
                timestamp=datetime.now(),
            )

        # 3. Update SystemMonitor
        if hasattr(self.app.state, "monitor"):
            await self.app.state.monitor.update_tick(symbol, price)

        # 4. Broadcast enriched TICK to frontend
        tick_payload = {
            "type": "TICK",
            "data": {
                **tick.model_dump(mode="json"),
                "source": source.value,
                "change": round(price_change, 2),
                "change_pct": round(price_change_pct, 4),
                "high": self._session_high.get(symbol, price),
                "low": self._session_low.get(symbol, price),
                "session_volume": self._session_volume.get(symbol, volume),
            },
        }
        await self.manager.broadcast(tick_payload)

    # ── Status Broadcast ─────────────────────────────────────────────────────

    async def _status_broadcast_loop(self):
        """Periodically broadcasts feed status to frontend."""
        while self.is_running:
            try:
                status = self.get_status()
                await self.manager.broadcast({
                    "type": "MARKET_STATUS",
                    "data": status,
                })
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Status broadcast error: {e}")

            await asyncio.sleep(5)

    # ── Static Test Helper ───────────────────────────────────────────────────

    @staticmethod
    async def test_connection():
        """Standalone test: tries to fetch a price from DNSE REST."""
        url = "https://services.entrade.com.vn/chart-api/v2/ohlcs/derivative"
        to_unix = int(datetime.now().timestamp())
        from_unix = to_unix - 600
        params = {"from": from_unix, "to": to_unix, "symbol": "VN30F1M", "resolution": "1"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if data.get("s") == "ok" and data.get("c"):
                    price = data["c"][-1]
                    print(f"✅ DNSE REST OK — VN30F1M latest: {price}")
                    return True
                else:
                    print(f"❌ DNSE REST response: {data.get('s')}")
                    return False
