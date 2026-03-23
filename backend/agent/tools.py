# backend/agent/tools.py
# LLM Tool definitions for function-calling (Claude / Gemini).
# Defines the 7 tools the AI agent can invoke to interact with markets.
# Phase 1: Stub with full tool schemas — execution implemented in Phase 3.

from loguru import logger


# ── Tool schemas (used directly by LLM SDK) ──────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "get_market_state",
        "description": (
            "Lấy OHLCV + chỉ báo kỹ thuật đã tính sẵn cho danh sách symbols "
            "và các khung thời gian được chỉ định."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Danh sách mã chứng khoán (e.g. ['VN30F2406', 'HPG'])",
                },
                "timeframes": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["1m", "5m", "15m", "1h", "1D"]},
                    "description": "Các khung thời gian cần lấy dữ liệu",
                },
            },
            "required": ["symbols", "timeframes"],
        },
    },
    {
        "name": "get_portfolio_state",
        "description": "Lấy số dư tài khoản, vị thế đang mở, PnL thực tế, và margin khả dụng.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "calculate_risk_metrics",
        "description": "Tính Kelly size, R/R ratio, và % rủi ro trên NAV cho một lệnh đề xuất.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Mã chứng khoán"},
                "entry": {"type": "number", "description": "Giá vào lệnh"},
                "stop_loss": {"type": "number", "description": "Giá cắt lỗ"},
                "direction": {
                    "type": "string",
                    "enum": ["LONG", "SHORT"],
                    "description": "Chiều giao dịch",
                },
            },
            "required": ["symbol", "entry", "stop_loss", "direction"],
        },
    },
    {
        "name": "place_order",
        "description": "Đặt lệnh thực qua TCBS API (paper mode nếu TCBS_PAPER_MODE=true).",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "direction": {"type": "string", "enum": ["LONG", "SHORT"]},
                "order_type": {"type": "string", "enum": ["LO", "ATO", "ATC"]},
                "quantity": {"type": "integer", "description": "Số lượng (lô)"},
                "price": {"type": ["number", "null"], "description": "Giá LO, null cho ATO/ATC"},
                "stop_loss": {"type": "number"},
                "take_profit": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Danh sách giá chốt lời [TP1, TP2]",
                },
                "rationale": {"type": "string", "description": "Lý do vào lệnh của AI"},
            },
            "required": ["symbol", "direction", "order_type", "quantity", "stop_loss", "take_profit", "rationale"],
        },
    },
    {
        "name": "modify_order",
        "description": "Điều chỉnh stop-loss trailing hoặc chốt lời từng phần cho lệnh đang mở.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "new_stop_loss": {"type": ["number", "null"], "description": "Giá SL mới, null nếu không đổi"},
                "close_percentage": {"type": ["integer", "null"], "description": "% đóng vị thế (1-100)"},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "close_position",
        "description": "Đóng vị thế một phần hoặc toàn bộ theo symbol.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "percentage": {"type": "integer", "description": "Phần trăm đóng (1-100)"},
                "reason": {"type": "string", "description": "Lý do đóng vị thế"},
                "urgency": {"type": "string", "enum": ["NORMAL", "EMERGENCY"]},
            },
            "required": ["symbol", "percentage", "reason", "urgency"],
        },
    },
    {
        "name": "send_notification",
        "description": "Gửi Telegram alert cho người dùng.",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["TRADE", "ALERT", "REPORT"]},
                "message": {"type": "string", "description": "Nội dung thông báo"},
            },
            "required": ["type", "message"],
        },
    },
]


class AgentTools:
    """
    Executor for LLM-invoked tools.
    Maps tool names to async handler methods.

    Phase 3 implementation will connect each method to the real
    data layer, risk engine, and TCBS connector.
    """

    async def dispatch(self, tool_name: str, params: dict) -> dict:
        """Route a tool call from the LLM to the correct handler."""
        handlers = {
            "get_market_state": self.get_market_state,
            "get_portfolio_state": self.get_portfolio_state,
            "calculate_risk_metrics": self.calculate_risk_metrics,
            "place_order": self.place_order,
            "modify_order": self.modify_order,
            "close_position": self.close_position,
            "send_notification": self.send_notification,
        }
        handler = handlers.get(tool_name)
        if not handler:
            raise ValueError(f"Unknown tool: {tool_name}")
        logger.debug(f"Tool dispatch: {tool_name}({params})")
        return await handler(**params)

    async def get_market_state(self, symbols: list[str], timeframes: list[str]) -> dict:
        """TODO (Phase 3): Fetch OHLCV + indicators from cache."""
        raise NotImplementedError

    async def get_portfolio_state(self) -> dict:
        """TODO (Phase 3): Fetch portfolio from TCBS connector."""
        raise NotImplementedError

    async def calculate_risk_metrics(self, symbol: str, entry: float, stop_loss: float, direction: str) -> dict:
        """TODO (Phase 3): Run Kelly + R/R calculation."""
        raise NotImplementedError

    async def place_order(self, **kwargs) -> dict:
        """TODO (Phase 3): Route order to TCBS connector (paper or live)."""
        raise NotImplementedError

    async def modify_order(self, order_id: str, **kwargs) -> dict:
        """TODO (Phase 3): Modify trailing stop or partial close."""
        raise NotImplementedError

    async def close_position(self, symbol: str, percentage: int, reason: str, urgency: str) -> dict:
        """TODO (Phase 3): Close position via TCBS."""
        raise NotImplementedError

    async def send_notification(self, type: str, message: str) -> dict:
        """TODO (Phase 3): Send Telegram message."""
        raise NotImplementedError
