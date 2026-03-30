import asyncio
from typing import Optional, Dict, Any, Union
from loguru import logger
from telegram import Bot
from telegram.constants import ParseMode
from datetime import datetime

from shared.models import TradeIntent, OrderReceipt
from shared.enums import TradeAction, OrderStatus

class TelegramNotifier:
    """
    Sends structured notifications to a configured Telegram chat.
    Supports standardized trading events and safety alerts.
    """

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.bot: Optional[Bot] = None
        
        if bot_token and chat_id:
            try:
                self.bot = Bot(token=bot_token)
                logger.info(f"TelegramNotifier initialized for chat: {chat_id}")
            except Exception as e:
                logger.error(f"Failed to initialize Telegram Bot: {e}")
        else:
            logger.warning("Telegram credentials missing — notifications will be logged but not sent.")

    async def send_message(self, text: str, parse_mode: str = ParseMode.HTML) -> bool:
        """Helper to send a message safely with error handling."""
        if self.bot is None or not self.chat_id:
            logger.debug(f"[MOCK-TELEGRAM] {text}")
            return False
            
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode
            )
            return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    async def send_trade_signal(self, intent: TradeIntent) -> None:
        """Formats and sends a strategy signal notification."""
        emoji = "🔭"
        
        message = (
            f"<b>{emoji} STRATEGY SIGNAL DETECTED</b>\n\n"
            f"<b>Symbol:</b> {intent.symbol}\n"
            f"<b>Action:</b> {intent.action}\n"
            f"<b>Confidence:</b> {intent.confidence}%\n"
            f"<b>Reason ({intent.ai_source.upper()}):</b> {intent.reason}\n"
            f"<b>Time:</b> {intent.created_at.strftime('%H:%M:%S')}\n"
            f"\n<i>#Signal #{intent.symbol}</i>"
        )
        await self.send_message(message)

    async def send_trade_alert(self, trade: Union[Dict[str, Any], OrderReceipt]) -> None:
        """Formats and sends a trade execution notification."""
        if isinstance(trade, OrderReceipt):
            data = trade.model_dump()
        else:
            data = trade

        symbol = data.get("symbol", "UNKNOWN")
        action = data.get("action", "ACTION")
        price = data.get("filled_price") or data.get("price") or 0.0
        qty = data.get("qty") or data.get("quantity", 1)
        status = data.get("status", "PENDING")
        
        emoji = "🟢 BUY" if action == "BUY" else "🔴 SELL"
        paper_tag = " [PAPER]" if data.get("paper_mode") else " [LIVE]"
        
        message = (
            f"<b>{emoji} ORDER EXECUTED{paper_tag}</b>\n\n"
            f"<b>Status:</b> {status}\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Price:</b> {price:,.2f}\n"
            f"<b>Quantity:</b> {qty}\n"
            f"<b>Time:</b> {datetime.now().strftime('%H:%M:%S')}\n"
            f"\n<i>#{symbol} #TradeFilled</i>"
        )
        await self.send_message(message)

    async def send_risk_rejection(self, intent: TradeIntent, reason: str) -> None:
        """Sends a detailed risk rejection alert."""
        message = (
            f"<b>🛡️ RISK REJECTED</b>\n\n"
            f"<b>Action:</b> {intent.action} {intent.symbol}\n"
            f"<b>Reason:</b> {reason}\n"
            f"<b>Time:</b> {datetime.now().strftime('%H:%M:%S')}"
        )
        await self.send_message(message)

    async def send_broker_rejection(self, symbol: str, action: str, error: str) -> None:
        """Sends a broker-level order rejection alert."""
        message = (
            f"<b>🚨 BROKER REJECTED ORDER</b>\n\n"
            f"<b>Order:</b> {action} {symbol}\n"
            f"<b>Error:</b> {error}\n"
            f"<b>Time:</b> {datetime.now().strftime('%H:%M:%S')}"
        )
        await self.send_message(message)

    async def send_system_event(self, event_name: str, details: str) -> None:
        """Sends a system-level event notification (Reconnect, KillSwitch, etc)."""
        icon = "⚙️"
        if "RECONNECT" in event_name.upper(): icon = "🔄"
        if "KILL" in event_name.upper(): icon = "🛑"
        
        message = (
            f"<b>{icon} SYSTEM EVENT: {event_name}</b>\n\n"
            f"<b>Details:</b> {details}\n"
            f"<b>Time:</b> {datetime.now().strftime('%H:%M:%S')}"
        )
        await self.send_message(message)

    async def send_alert(self, message: str, level: str = "INFO") -> None:
        """Sends a generic alert message with severity emoticons."""
        level_map = {
            "ERROR": "🚨 ERROR",
            "WARNING": "⚠️ WARNING",
            "RISK": "🛡️ RISK",
            "INFO": "ℹ️ INFO",
            "SYSTEM": "⚙️ SYSTEM"
        }
        prefix = level_map.get(level.upper(), "ℹ️ INFO")
        text = f"<b>{prefix}:</b> {message}"
        await self.send_message(text)

    async def send_daily_report(self, report: dict) -> None:
        """Sends end-of-day performance report."""
        text = "<b>📊 DAILY PERFORMANCE REPORT</b>\n\n"
        for key, val in report.items():
            text += f"• {key}: {val}\n"
        await self.send_message(text)
