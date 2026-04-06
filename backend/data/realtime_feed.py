# backend/data/realtime_feed.py
# Realtime market data feed using DNSE MQTT-over-WSS as primary source
# with REST polling fallback.

import asyncio
import json
import random
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional

import aiohttp
import paho.mqtt.client as mqtt
from loguru import logger

from config.settings import settings
from data.cache import save_tick
from data.normalizer import TickData


def is_vn_market_open() -> bool:
    """Checks if current time is within Vietnam trading hours."""
    vn_tz = timezone(timedelta(hours=7))
    now = datetime.now(vn_tz)

    if now.weekday() >= 5:
        return False

    current_time = now.time()
    morning_start = now.replace(hour=8, minute=45, second=0, microsecond=0).time()
    morning_end = now.replace(hour=11, minute=30, second=0, microsecond=0).time()
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
      1. DNSE MQTT over secure WebSocket
      2. DNSE REST polling
      3. Mock prices for development
    """

    DNSE_REST_URL = "https://services.entrade.com.vn/chart-api/v2/ohlcs"
    DNSE_AUTH_URL = "https://api.dnse.com.vn/user-service/api/auth"
    DNSE_ME_URL = "https://api.dnse.com.vn/user-service/api/me"
    DNSE_MQTT_HOST = "datafeed-lts-krx.dnse.com.vn"
    DNSE_MQTT_PORT = 443
    DNSE_MQTT_PATH = "/wss"

    def __init__(self, app, websocket_manager, symbols: list[str] | None = None, poll_interval_sec: float = 5.0):
        self.app = app
        self.manager = websocket_manager
        self.symbols = symbols or ["VN30F1M"]
        self.poll_interval = poll_interval_sec

        self.is_running = False
        self._ws_task: Optional[asyncio.Task] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._status_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._mqtt_client: Optional[mqtt.Client] = None
        self._mqtt_ready = False

        self.connection_status = ConnectionStatus.DISCONNECTED
        self.active_source = FeedSource.MOCK
        self.last_tick_at: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.reconnect_count = 0
        self._stale_threshold_sec = settings.stale_data_threshold_sec or 30

        self._jwt_token: Optional[str] = None
        self._investor_id: Optional[str] = None
        self._jwt_expires_at: float = 0

        self._mock_prices: Dict[str, float] = {"VN30F1M": 1760.0, "HPG": 27.50, "SSI": 35.20}
        self._last_prices: Dict[str, float] = {}
        self._session_high: Dict[str, float] = {}
        self._session_low: Dict[str, float] = {}
        self._session_volume: Dict[str, int] = {}

    def start(self):
        """Starts the realtime feed."""
        self.is_running = True
        self._loop = asyncio.get_running_loop()
        self.connection_status = ConnectionStatus.CONNECTING

        if settings.dnse_ws_enabled:
            self._ws_task = asyncio.create_task(self._ws_loop())
        else:
            self.connection_status = ConnectionStatus.CONNECTED
            self.active_source = FeedSource.DNSE_REST
            logger.info("DNSE WebSocket disabled by configuration. Using REST polling only.")

        self._poll_task = asyncio.create_task(self._poll_loop())
        self._status_task = asyncio.create_task(self._status_broadcast_loop())
        logger.info(f"RealtimeMarketFeed started - symbols: {self.symbols}, poll_interval: {self.poll_interval}s")

    def stop(self):
        """Stops the realtime feed."""
        self.is_running = False
        self.connection_status = ConnectionStatus.DISCONNECTED
        self._disconnect_mqtt()

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
                    logger.success(f"Synced {symbol} -> {price}")
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

    async def _authenticate_dnse(self) -> bool:
        """Authenticates with DNSE and stores MQTT credentials."""
        username = settings.dnse_username or ""
        password_secret = settings.dnse_password
        password = password_secret.get_secret_value() if password_secret is not None else ""

        if not username or not password:
            self._jwt_token = None
            self._investor_id = None
            logger.debug("DNSE MQTT auth unavailable: DNSE_USERNAME/DNSE_PASSWORD not configured.")
            return False

        if self._jwt_token and self._investor_id and time.time() < self._jwt_expires_at:
            return True

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.DNSE_AUTH_URL,
                    json={"username": username, "password": password},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"DNSE auth failed: HTTP {resp.status}")
                        return False

                    data = await resp.json()
                    token = data.get("token") or data.get("accessToken")
                    if not token:
                        logger.warning("DNSE auth failed: no token in response")
                        return False

                    async with session.get(
                        self.DNSE_ME_URL,
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as me_resp:
                        if me_resp.status != 200:
                            logger.warning(f"DNSE me() failed: HTTP {me_resp.status}")
                            return False

                        me_data = await me_resp.json()
                        investor_id = str(me_data.get("investorId", "")).strip()
                        if not investor_id:
                            logger.warning("DNSE me() failed: missing investorId")
                            return False

                        self._jwt_token = token
                        self._investor_id = investor_id
                        self._jwt_expires_at = time.time() + (7 * 3600)
                        logger.success(f"DNSE auth success - investor: {self._investor_id}")
                        return True
        except Exception as e:
            logger.warning(f"DNSE auth error: {e}")
            return False

    async def _ws_loop(self):
        """Main MQTT-over-WSS loop with reconnect."""
        backoff = 1.0
        max_backoff = 60.0

        while self.is_running:
            try:
                auth_ok = await self._authenticate_dnse()
                if not auth_ok:
                    self.last_error = "DNSE MQTT requires DNSE_USERNAME and DNSE_PASSWORD"
                    self.active_source = FeedSource.DNSE_REST
                    self.connection_status = ConnectionStatus.CONNECTED
                    logger.warning("DNSE MQTT auth unavailable. Falling back to REST polling.")
                    break

                self.connection_status = ConnectionStatus.CONNECTING
                await self._connect_mqtt()
                backoff = 1.0

                while self.is_running and self._mqtt_ready:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.last_error = str(e)
                logger.warning(f"DNSE MQTT error: {e}")
            finally:
                self._disconnect_mqtt()

            if not self.is_running:
                break

            self.active_source = FeedSource.DNSE_REST
            self.connection_status = ConnectionStatus.RECONNECTING
            self.reconnect_count += 1
            logger.info(f"DNSE MQTT reconnecting in {backoff:.1f}s (attempt #{self.reconnect_count})")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

    async def _connect_mqtt(self):
        """Connects to DNSE MQTT over secure WebSocket."""
        if not self._investor_id or not self._jwt_token:
            raise RuntimeError("Missing DNSE MQTT credentials")

        suffix = int(time.time())
        client_id = f"dnse-price-json-mqtt-ws-sub-{self._investor_id}-{suffix}"
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            transport="websockets",
            protocol=mqtt.MQTTv311,
        )
        client.ws_set_options(path=self.DNSE_MQTT_PATH)
        client.tls_set()
        client.username_pw_set(username=self._investor_id, password=self._jwt_token)
        client.reconnect_delay_set(min_delay=1, max_delay=30)

        client.on_connect = self._on_mqtt_connect
        client.on_disconnect = self._on_mqtt_disconnect
        client.on_message = self._on_mqtt_message
        client.on_subscribe = self._on_mqtt_subscribe

        logger.info(f"Connecting to DNSE MQTT: wss://{self.DNSE_MQTT_HOST}{self.DNSE_MQTT_PATH}")
        client.connect(self.DNSE_MQTT_HOST, self.DNSE_MQTT_PORT, keepalive=30)
        client.loop_start()
        self._mqtt_client = client

        for _ in range(20):
            if self._mqtt_ready:
                return
            await asyncio.sleep(0.5)

        raise TimeoutError("Timed out waiting for DNSE MQTT connection")

    def _disconnect_mqtt(self):
        """Stops MQTT client and clears local state."""
        if self._mqtt_client is not None:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception as e:
                logger.debug(f"MQTT disconnect cleanup error: {e}")
        self._mqtt_client = None
        self._mqtt_ready = False

    def _subscribe_topics(self, symbol: str):
        """Subscribes to DNSE MQTT topics for a symbol."""
        if not self._mqtt_client:
            return

        topics = [
            f"plaintext/quotes/krx/mdds/stockinfo/v1/roundlot/symbol/{symbol}",
            f"plaintext/quotes/krx/mdds/topprice/v1/roundlot/symbol/{symbol}",
            f"plaintext/quotes/krx/mdds/tick/v1/roundlot/symbol/{symbol}",
        ]
        for topic in topics:
            result, mid = self._mqtt_client.subscribe(topic, qos=0)
            if result == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"Subscribed to {topic} (mid={mid})")
            else:
                logger.warning(f"Subscribe failed for {topic}: {result}")

    def _on_mqtt_connect(self, client, userdata, flags, reason_code, properties=None):
        """Paho callback: connection acknowledged."""
        if getattr(reason_code, "is_failure", False):
            self.last_error = f"DNSE MQTT auth failed: {reason_code}"
            self.connection_status = ConnectionStatus.RECONNECTING
            self.active_source = FeedSource.DNSE_REST
            logger.warning(self.last_error)
            return

        self._mqtt_ready = True
        self.connection_status = ConnectionStatus.CONNECTED
        self.active_source = FeedSource.DNSE_WS
        self.last_error = None
        self.reconnect_count = 0
        logger.success(f"DNSE MQTT connected: {reason_code}")

        for symbol in self.symbols:
            self._subscribe_topics(symbol)

    def _on_mqtt_disconnect(self, client, userdata, flags, reason_code, properties=None):
        """Paho callback: disconnected."""
        self._mqtt_ready = False
        if not self.is_running:
            return

        self.active_source = FeedSource.DNSE_REST
        self.connection_status = ConnectionStatus.RECONNECTING
        self.last_error = f"DNSE MQTT disconnected: {reason_code}"
        logger.warning(self.last_error)

    def _on_mqtt_subscribe(self, client, userdata, mid, reason_codes, properties=None):
        """Paho callback: subscription ack."""
        logger.debug(f"DNSE MQTT subscribe ack mid={mid} reason_codes={reason_codes}")

    def _on_mqtt_message(self, client, userdata, msg):
        """Paho callback: forward MQTT payload into async parser."""
        if not self._loop:
            return

        payload = msg.payload.decode("utf-8", errors="ignore")
        asyncio.run_coroutine_threadsafe(self._handle_ws_message(payload), self._loop)

    async def _handle_ws_message(self, raw: str):
        """Parses incoming DNSE MQTT payload and emits ticks."""
        try:
            data = json.loads(raw)

            nested = data.get("content") if isinstance(data.get("content"), dict) else data.get("data")
            if isinstance(nested, dict):
                data = nested

            price = None
            symbol = None
            volume = 0

            if "lastPrice" in data:
                price = float(data["lastPrice"])
                symbol = data.get("symbol", data.get("stockSymbol", self.symbols[0]))
                volume = int(data.get("totalVolume", data.get("matchVolume", 0)))
            elif "lastMatchedPrice" in data:
                price = float(data["lastMatchedPrice"])
                symbol = data.get("symbol", self.symbols[0])
                volume = int(data.get("totalVolume", data.get("matchedVolume", 0)))
            elif "matchPrice" in data:
                price = float(data["matchPrice"])
                symbol = data.get("symbol", data.get("stockSymbol", self.symbols[0]))
                volume = int(data.get("matchVolume", 0))
            elif "c" in data and isinstance(data["c"], (int, float)):
                price = float(data["c"])
                symbol = data.get("s", data.get("symbol", self.symbols[0]))
                volume = int(data.get("v", 0))
            elif "price" in data:
                price = float(data["price"])
                symbol = data.get("symbol", self.symbols[0])
                volume = int(data.get("volume", 0))

            if price and price > 0 and symbol:
                await self._emit_tick(symbol, price, volume, FeedSource.DNSE_WS)
        except json.JSONDecodeError:
            logger.debug("Ignoring non-JSON MQTT payload")
        except Exception as e:
            logger.debug(f"MQTT message parse error: {e}")

    async def _poll_loop(self):
        """REST polling fallback."""
        await asyncio.sleep(3.0)

        while self.is_running:
            try:
                if self.active_source == FeedSource.DNSE_WS and self.connection_status == ConnectionStatus.CONNECTED:
                    if self.last_tick_at:
                        elapsed = (datetime.now(timezone.utc) - self.last_tick_at).total_seconds()
                        if elapsed < self._stale_threshold_sec:
                            await asyncio.sleep(self.poll_interval)
                            continue

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
                    if market_open:
                        for symbol in self.symbols:
                            await self._emit_mock_tick(symbol)
                        self.active_source = FeedSource.MOCK
                    else:
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
        """Fetches latest price from DNSE REST API."""
        endpoint = "derivative" if symbol.startswith("VN30F") else "stock"
        query_symbol = "VN30F1M" if symbol.startswith("VN30F") else symbol

        to_unix = int(datetime.now().timestamp())
        from_unix = to_unix - 86400
        url = f"{self.DNSE_REST_URL}/{endpoint}"
        params = {
            "from": from_unix,
            "to": to_unix,
            "symbol": query_symbol,
            "resolution": "1",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return None

                    data = await resp.json()
                    closes = data.get("c", [])
                    volumes = data.get("v", [])
                    if closes:
                        price = float(closes[-1])
                        if volumes:
                            self._session_volume[symbol] = int(sum(volumes[-10:]))
                        return price
        except Exception as e:
            logger.debug(f"DNSE REST fetch error for {symbol}: {e}")
        return None

    async def _emit_mock_tick(self, symbol: str):
        """Generates a mock tick when real data is unavailable."""
        base = self._mock_prices.get(symbol, 1760.0)
        noise = random.uniform(-0.0001, 0.0001)
        new_price = round(base * (1 + noise), 2)
        self._mock_prices[symbol] = new_price
        await self._emit_tick(symbol, new_price, random.randint(1, 100), FeedSource.MOCK)

    async def _emit_tick(self, symbol: str, price: float, volume: int, source: FeedSource):
        """Central tick processing: save, update state, broadcast."""
        now = datetime.now(timezone.utc)

        prev_price = self._last_prices.get(symbol, price)
        price_change = price - prev_price
        price_change_pct = (price_change / prev_price * 100) if prev_price > 0 else 0

        self._last_prices[symbol] = price
        if symbol not in self._session_high or price > self._session_high[symbol]:
            self._session_high[symbol] = price
        if symbol not in self._session_low or price < self._session_low[symbol]:
            self._session_low[symbol] = price

        self.last_tick_at = now

        tick = TickData(
            symbol=symbol,
            price=price,
            volume=volume,
            timestamp=now,
            is_buyer_maker=random.choice([True, False]),
        )

        if hasattr(self.app.state, "redis"):
            await save_tick(self.app.state.redis, symbol, tick)

        if hasattr(self.app.state, "market_cache"):
            self.app.state.market_cache.update_snapshot(
                symbol=symbol,
                price=price,
                volume=self._session_volume.get(symbol, volume),
                timestamp=datetime.now(),
            )

        if hasattr(self.app.state, "monitor"):
            await self.app.state.monitor.update_tick(symbol, price)

        if hasattr(self.app.state, "signal_journal"):
            try:
                await self.app.state.signal_journal.sync_market_price(symbol, price, now)
            except Exception as e:
                logger.debug(f"Signal journal sync failed for {symbol}: {e}")

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

    async def _status_broadcast_loop(self):
        """Periodically broadcasts feed status."""
        while self.is_running:
            try:
                await self.manager.broadcast({"type": "MARKET_STATUS", "data": self.get_status()})
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Status broadcast error: {e}")

            await asyncio.sleep(5)

    @staticmethod
    async def test_connection():
        """Standalone test helper using DNSE REST."""
        url = "https://services.entrade.com.vn/chart-api/v2/ohlcs/derivative"
        to_unix = int(datetime.now().timestamp())
        from_unix = to_unix - 600
        params = {"from": from_unix, "to": to_unix, "symbol": "VN30F1M", "resolution": "1"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                closes = data.get("c", [])
                if closes:
                    print(f"DNSE REST OK -> VN30F1M latest: {closes[-1]}")
                    return True
                print(f"DNSE REST response invalid: {data}")
                return False
