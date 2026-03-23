# backend/agent/core.py
# Main AI trading agent loop.
# Orchestrates market analysis, LLM reasoning, decision gate, execution,
# position management, and cycle logging every N seconds (configurable).
# Phase 1: Stub — fully implemented in Phase 3.

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from loguru import logger


SYSTEM_PROMPT = """
Bạn là AI Trading Agent chuyên thị trường chứng khoán Việt Nam.

Tư duy kết hợp: Paul Tudor Jones (risk mgmt) + Jesse Livermore
(tape reading) + Stanley Druckenmiller (macro timing).

NGUYÊN TẮC BẤT BIẾN:
- Bảo toàn vốn > mọi thứ khác
- Chỉ vào lệnh khi confluence >= 6/10
- Không bao giờ risk > 2% NAV/lệnh
- Trailing stop bắt buộc sau khi lời >= 1×ATR

MARKET REGIME (xác định mỗi đầu phiên):
TRENDING_UP | TRENDING_DOWN | RANGING | HIGH_VOLATILITY

Mỗi quyết định PHẢI có format JSON:
{
  "regime": "...",
  "confluence_score": X/10,
  "confluence_factors": [...],
  "entry": price,
  "stop_loss": price,
  "take_profit": [tp1, tp2],
  "risk_pct_nav": X,
  "reward_risk": X,
  "confidence": X,
  "action": "EXECUTE|WAIT|SKIP",
  "rationale": "..."
}
"""


class AITradingAgent:
    """
    Vòng lặp agent chính. Sử dụng LLM (Claude/Gemini) để:
    1. Nhận thức trạng thái thị trường (Market Awareness)
    2. Suy luận và đánh giá rủi ro (Reasoning & Risk)
    3. Ra quyết định giao dịch (Decision Gate)
    4. Thực thi và quản lý vị thế (Execution & Management)
    5. Log và thông báo (Logging & Notification)

    Phase 3 implementation adds:
    - Real LLM integration (Gemini / Claude function calling)
    - Full strategy evaluation
    - Decision Gate with 9 hard blocks
    - Active position management with trailing stops
    - Telegram notifications
    """

    SYSTEM_PROMPT = SYSTEM_PROMPT

    def __init__(self, cycle_interval: int = 30) -> None:
        self.cycle_interval = cycle_interval
        self.is_running = False
        self.cycle_count = 0
        logger.info(f"AITradingAgent initialized — cycle={cycle_interval}s [STUB]")

    async def run(self) -> None:
        """
        Start the continuous agent loop.
        Runs indefinitely until stop() is called.
        """
        self.is_running = True
        logger.info("🤖 AI Trading Agent loop STARTED")
        while self.is_running:
            try:
                await self.run_cycle()
                await asyncio.sleep(self.cycle_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Agent cycle error: {e}")
                await asyncio.sleep(self.cycle_interval)
        logger.info("🤖 AI Trading Agent loop STOPPED")

    async def stop(self) -> None:
        """Gracefully stop the agent loop."""
        self.is_running = False

    async def run_cycle(self) -> dict:
        """
        TODO (Phase 3): Execute one full agent decision cycle.
        Returns the decision dict from the LLM.
        """
        self.cycle_count += 1
        logger.info(f"Agent cycle #{self.cycle_count} — [STUB, not yet implemented]")
        return {
            "cycle": self.cycle_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "WAIT",
            "rationale": "Agent core not yet implemented (Phase 3)",
        }

    async def manage_open_positions(self) -> None:
        """TODO (Phase 3): Check trailing stops and partial TP on open positions."""
        raise NotImplementedError("AITradingAgent.manage_open_positions() — Phase 3")

    async def emergency_stop(self, reason: str) -> None:
        """
        TODO (Phase 3): KILLSWITCH — close all positions immediately.
        Called when circuit breaker drawdown threshold is breached.
        """
        logger.critical(f"🚨 EMERGENCY STOP triggered: {reason}")
        raise NotImplementedError("AITradingAgent.emergency_stop() — Phase 3")
