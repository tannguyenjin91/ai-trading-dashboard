# backend/execution/risk_engine.py
from datetime import datetime
from typing import Optional, List, Dict, Any
from loguru import logger
from shared.models import TradeIntent, RiskResult
from shared.enums import RiskStatus, TradeAction

class RiskEngine:
    """
    Centralized risk management gatekeeper.
    Performs pre-trade checks and applies safety limits.
    """
    def __init__(self, settings: Any):
        self.settings = settings
        self.is_kill_switch_active = False 
        self.last_signal_times: Dict[str, datetime] = {} # symbol -> time

    async def validate_intent(
        self, 
        intent: TradeIntent, 
        portfolio: Dict[str, Any], 
        active_positions: List[Dict[str, Any]],
        monitor: Any = None,
        last_candle_time: Optional[datetime] = None
    ) -> RiskResult:
        """
        Runs a suite of risk checks on the proposed TradeIntent.
        """
        # 1. Kill Switch Check (Centralized Monitor)
        if monitor and monitor.is_kill_switch_active:
            return RiskResult(is_approved=False, status=RiskStatus.REJECTED, reason="KILL SWITCH IS ACTIVE (via Monitor)")

        # 1b. Live Trading Enforcement
        is_live_intent = not getattr(intent, 'paper_mode', True)
        live_enabled = monitor.is_live_trading_enabled if monitor else self.settings.live_trading
        
        if live_enabled is False and is_live_intent:
             return RiskResult(is_approved=False, status=RiskStatus.REJECTED, reason="LIVE TRADING IS DISABLED (via Monitor/Settings)")

        # 2. Trading Session Check
        if not self._is_trading_session_valid():
            return RiskResult(is_approved=False, status=RiskStatus.REJECTED, reason="OUTSIDE TRADING SESSION")

        # 2b. Stale Data Check
        if last_candle_time:
            age = (datetime.now() - last_candle_time).total_seconds()
            threshold = getattr(self.settings, "stale_data_threshold_sec", 60)
            if age > threshold:
                return RiskResult(is_approved=False, status=RiskStatus.REJECTED, reason=f"STALE MARKET DATA ({age:.1f}s > {threshold}s)")

        # 3. Symbol Tradability Check
        if not self._is_symbol_tradable(intent.symbol):
            return RiskResult(is_approved=False, status=RiskStatus.REJECTED, reason=f"SYMBOL {intent.symbol} NOT TRADABLE")

        # 4. Duplicate Signal Prevention (Within time window)
        last_time = self.last_signal_times.get(intent.symbol)
        if last_time:
            elapsed = (datetime.now() - last_time).total_seconds()
            window = getattr(self.settings, "duplicate_signal_window_sec", 300)
            if elapsed < window:
                return RiskResult(is_approved=False, status=RiskStatus.REJECTED, reason=f"DUPLICATE SIGNAL (Blocked for {window}s, last was {elapsed:.1f}s ago)")

        # 4b. Active Position Check
        for pos in active_positions:
            if pos.get("symbol") == intent.symbol:
                return RiskResult(is_approved=False, status=RiskStatus.REJECTED, reason=f"ALREADY HAVE ACTIVE POSITION IN {intent.symbol}")

        # 5. Quantity Calculation & Limits
        nav = portfolio.get("balance", 0)
        if nav <= 0:
            return RiskResult(is_approved=False, status=RiskStatus.REJECTED, reason="INSUFFICIENT NAV (<=0)")

        calculated_qty = await self._calculate_quantity(intent, nav)
        
        if calculated_qty <= 0:
            return RiskResult(is_approved=False, status=RiskStatus.REJECTED, reason="QUANTITY CALCULATION RETURNED ZERO")

        # Position Size Limit
        max_qty = getattr(self.settings, "max_position_size", 5)
        if calculated_qty > max_qty:
            logger.warning(f"Quantity {calculated_qty} exceeds max limit {max_qty}. Capping at {max_qty}.")
            calculated_qty = max_qty

        # Record success time for duplicate prevention
        self.last_signal_times[intent.symbol] = datetime.now()

        return RiskResult(
            is_approved=True,
            status=RiskStatus.APPROVED,
            adjusted_qty=int(calculated_qty),
            reason="All risk checks passed."
        )

    def _is_trading_session_valid(self) -> bool:
        """Checks if current time is within VN trading hours (9:00 - 14:30)."""
        now = datetime.now().time()
        # Mocking or strictly checking settings for dev mode
        if hasattr(self.settings, "is_development") and self.settings.is_development:
            return True
            
        start = now.replace(hour=9, minute=0, second=0, microsecond=0)
        end = now.replace(hour=14, minute=45, second=0, microsecond=0) # Incl. ATC
        return start <= now <= end

    def _is_symbol_tradable(self, symbol: str) -> bool:
        """Simple whitelist for VN30F futures."""
        return "VN30F" in symbol or symbol in ["TCB", "VPB", "FPT", "VIC", "VHM"]

    async def _calculate_quantity(self, intent: TradeIntent, nav: float) -> int:
        """
        Calculates position size based on risk settings.
        Simplification: 1 contract for VN30F, or % of NAV for stocks.
        """
        if "VN30F" in intent.symbol:
            return 1 # Default for futures in paper mode
            
        if intent.entry_price and intent.stop_loss and intent.entry_price != intent.stop_loss:
            # Risk-based sizing: Risk % of NAV per trade
            risk_pct = getattr(self.settings, "max_risk_per_trade_pct", 1.0)
            risk_amount = nav * (risk_pct / 100.0)
            risk_per_share = abs(intent.entry_price - intent.stop_loss)
            qty = risk_amount / risk_per_share
            return int(max(0, qty))
            
        # Fallback: 5% of NAV
        if intent.entry_price:
            return int((nav * 0.05) / intent.entry_price)
            
        return 0
