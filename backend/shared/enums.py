# backend/shared/enums.py
from enum import Enum

class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    LONG = "LONG"
    SHORT = "SHORT"
    CLOSE = "CLOSE"

class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    MTL = "MTL"
    ATO = "ATO"
    ATC = "ATC"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"

class RiskStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WARNING = "WARNING"
