# backend/monitoring/system_monitor.py
from datetime import datetime
from typing import Dict, Any, Optional
from loguru import logger

class SystemMonitor:
    """
    Central monitoring hub for system state, safety status, and performance metrics.
    Acts as a source of truth for the Dashboard.
    """
    def __init__(self, settings: Any):
        self.settings = settings
        self.is_kill_switch_active = False
        self.is_live_trading_enabled = getattr(settings, "live_trading", False)
        self.start_time = datetime.now()
        self.last_heartbeat = datetime.now()
        self.session_stats = {
            "trades_count": 0,
            "rejections_count": 0,
            "errors_count": 0,
            "ws_connected": False
        }

    def update_heartbeat(self, status: str = "ALIVE"):
        """Called by main loops to indicate they are running."""
        self.last_heartbeat = datetime.now()
        logger.trace(f"System heartbeat: {status}")

    def toggle_kill_switch(self, active: bool):
        """Emergency stop toggled from Dashboard."""
        self.is_kill_switch_active = active
        status = "ACTIVATED" if active else "DEACTIVATED"
        logger.warning(f"🚨 KILL SWITCH {status} via Monitor")

    def toggle_live_trading(self, active: bool):
        """Production mode toggled from Dashboard."""
        self.is_live_trading_enabled = active
        status = "ENABLED" if active else "DISABLED"
        logger.warning(f"⚙️ LIVE TRADING {status} via Monitor")

    def get_status_summary(self) -> Dict[str, Any]:
        """Provides a complete snapshot for the frontend."""
        return {
            "uptime_sec": int((datetime.now() - self.start_time).total_seconds()),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "is_kill_switch_active": self.is_kill_switch_active,
            "is_live_trading_enabled": self.is_live_trading_enabled,
            "stats": self.session_stats,
            "safety": {
                "stale_threshold_sec": getattr(self.settings, "stale_data_threshold_sec", 60),
                "duplicate_window_sec": getattr(self.settings, "duplicate_signal_window_sec", 300)
            }
        }

    def record_event(self, event_type: str):
        """Increments counters for dashboard stats."""
        if event_type in self.session_stats:
            self.session_stats[event_type] += 1

    async def update_tick(self, symbol: str, price: float):
        """Placeholder for Phase 4 position monitoring updates."""
        # This will eventually update PnL on active positions in real-time
        pass
