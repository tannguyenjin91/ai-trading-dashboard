# backend/api/monitor.py
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

router = APIRouter(prefix="/v1/monitor", tags=["Monitoring"])

class ToggleRequest(BaseModel):
    active: bool

@router.get("/status")
async def get_system_status(request: Request):
    """Returns the current system health and safety status."""
    monitor = request.app.state.monitor
    return monitor.get_status_summary()

@router.post("/kill-switch")
async def toggle_kill_switch(request: Request, payload: ToggleRequest):
    """Triggers or deactivates the global emergency stop."""
    monitor = request.app.state.monitor
    monitor.toggle_kill_switch(payload.active)
    
    # Notify via Telegram if possible
    if hasattr(request.app.state, "notifier"):
        status = "🔴 ACTIVATED" if payload.active else "🟢 DEACTIVATED"
        await request.app.state.notifier.send_system_event("KILL SWITCH", f"Manual trigger from Dashboard: {status}")
        
    return {"status": "success", "kill_switch_active": payload.active}

@router.post("/toggle-live")
async def toggle_live_trading(request: Request, payload: ToggleRequest):
    """Enables or disables production-mode execution."""
    monitor = request.app.state.monitor
    monitor.toggle_live_trading(payload.active)
    
    if hasattr(request.app.state, "notifier"):
        status = "⚠️ ENABLED" if payload.active else "🛡️ DISABLED"
        await request.app.state.notifier.send_system_event("LIVE TRADING", f"Manual change from Dashboard: {status}")
        
    return {"status": "success", "live_trading_enabled": payload.active}
