# backend/shared/exceptions.py
from typing import Any

class BrokerError(Exception):
    """Base class for all broker-related errors."""
    def __init__(self, message: str, original_error: Any = None):
        super().__init__(message)
        self.original_error = original_error

class AuthError(BrokerError):
    """Raised when authentication with the broker fails (e.g., invalid TOTP, password)."""
    pass

class NetworkError(BrokerError):
    """Raised when there are connectivity issues with the broker's API or WebSocket."""
    pass

class RejectError(BrokerError):
    """Raised when the broker rejects an order (e.g., insufficient margin, price out of range)."""
    def __init__(self, message: str, reject_code: str = "UNKNOWN"):
        super().__init__(message)
        self.reject_code = reject_code

class ValidationError(BrokerError):
    """Raised when the order request doesn't meet the broker's minimum requirements."""
    pass

class RateLimitError(BrokerError):
    """Raised when the broker's API rate limit is exceeded."""
    pass

class ReconnectError(BrokerError):
    """Raised when the session cannot be re-established after multiple attempts."""
    pass
