# backend/config/__init__.py
# Config package for vn-ai-trader backend.

from .settings import settings
from .logging import setup_logging, logger

__all__ = ["settings", "setup_logging", "logger"]
