# backend/config/logging.py
# Loguru structured logging configuration for vn-ai-trader.
# Outputs JSON to stdout and rotating file sink under logs/.

import sys
from pathlib import Path
from loguru import logger


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure Loguru with:
    - Colored, human-readable output to stdout (development)
    - JSON structured output to rotating log file (all environments)

    Call once at application startup in main.py lifespan.
    """
    # Remove default handler
    logger.remove()

    # ── Stdout handler ──────────────────────────────────────────────────────
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    )
    logger.add(
        sys.stdout,
        format=log_format,
        level=log_level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # ── File handler (JSON, rotating) ───────────────────────────────────────
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger.add(
        log_dir / "app.log",
        format="{time} | {level} | {name}:{function}:{line} — {message}",
        level=log_level,
        rotation="50 MB",
        retention="14 days",
        compression="zip",
        serialize=True,   # JSON output
        backtrace=True,
        diagnose=False,   # No sensitive data in prod logs
    )

    logger.info(f"Logging initialized — level={log_level}")


# Re-export logger for use across the application
__all__ = ["logger", "setup_logging"]
