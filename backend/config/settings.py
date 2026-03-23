# backend/config/settings.py
# Pydantic v2 settings loaded from .env file.
# All application configuration is centralized here.

from enum import Enum
from pydantic import Field, field_validator, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AIModel(str, Enum):
    """Supported AI model providers."""
    GEMINI = "gemini"
    CLAUDE = "claude"


class Environment(str, Enum):
    """Deployment environments."""
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables / .env file.
    All fields map directly to variables in .env.example.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── AI Models ───────────────────────────────────────────────────────────
    gemini_api_key: SecretStr = Field(default="", description="Google Gemini API key")
    anthropic_api_key: SecretStr = Field(default="", description="Anthropic Claude API key")
    dnse_api_key: SecretStr = Field(default="", description="DNSE API key")
    default_ai_model: AIModel = Field(default=AIModel.GEMINI, description="Default LLM provider")

    # ─── TCBS Broker ─────────────────────────────────────────────────────────
    tcbs_username: str = Field(default="", description="TCBS login username")
    tcbs_password: str = Field(default="", description="TCBS login password")
    tcbs_totp_secret: SecretStr = Field(default="", description="TOTP secret for 2FA")
    tcbs_account_no: str = Field(default="", description="TCBS account number")
    tcbs_paper_mode: bool = Field(default=True, description="Paper trading mode (no real orders)")

    # ─── Redis ───────────────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    redis_ttl_tick: int = Field(default=1, description="Tick data cache TTL in seconds")
    redis_ttl_ohlcv: int = Field(default=300, description="OHLCV cache TTL in seconds")

    # ─── Risk Management ─────────────────────────────────────────────────────
    live_trading: bool = Field(default=False, description="Master switch for live trading")
    stale_data_threshold_sec: int = Field(default=60, description="Max allowed age for market data")
    duplicate_signal_window_sec: int = Field(default=300, description="Seconds to block duplicate signals")
    max_position_size: int = Field(default=5, description="Max contracts/shares per symbol")
    max_risk_per_trade_pct: float = Field(default=2.0, description="Max risk per trade as % of NAV")
    max_daily_drawdown_pct: float = Field(default=5.0, description="Daily drawdown killswitch threshold")
    agent_cycle_interval: int = Field(default=30, description="Seconds between agent loop runs")
    min_confluence_score: int = Field(default=6, description="Minimum /10 confluence to execute")
    min_reward_risk: float = Field(default=2.0, description="Minimum reward:risk ratio")
    min_confidence_pct: float = Field(default=70.0, description="Minimum AI confidence % to execute")

    # ─── Circuit Breakers ────────────────────────────────────────────────────
    drawdown_reduce_pct: float = Field(default=2.0, description="Drawdown % to trigger 50% size reduction")
    drawdown_scalping_pct: float = Field(default=3.0, description="Drawdown % to enter scalping-only mode")
    drawdown_close_only_pct: float = Field(default=4.0, description="Drawdown % to enter close-only mode")
    drawdown_killswitch_pct: float = Field(default=5.0, description="Drawdown % triggers killswitch")

    # ─── Telegram ────────────────────────────────────────────────────────────
    telegram_bot_token: SecretStr = Field(default="", description="Telegram bot token")
    telegram_chat_id: SecretStr = Field(default="", description="Telegram chat ID for notifications")

    # ─── Database ────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///./audit.db",
        description="SQLAlchemy async database URL",
    )

    # ─── Server ──────────────────────────────────────────────────────────────
    environment: Environment = Field(default=Environment.DEVELOPMENT)
    log_level: str = Field(default="INFO")
    cors_origins: str = Field(default="http://localhost:5173")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    @field_validator("max_risk_per_trade_pct")
    @classmethod
    def validate_risk(cls, v: float) -> float:
        """Hard cap: never allow more than 5% risk per trade."""
        if v > 5.0:
            raise ValueError("max_risk_per_trade_pct cannot exceed 5.0% — safety constraint")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT


# Singleton instance — import this throughout the app
settings = Settings()
