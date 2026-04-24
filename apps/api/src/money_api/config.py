from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    app_bind: str = "127.0.0.1"
    app_port_api: int = 8000
    tz: str = "Asia/Ho_Chi_Minh"
    default_currency: str = "VND"
    locale: str = "vi-VN"

    app_encryption_key: str = Field(default="dev-only-insecure-replace-me-with-random-32")
    session_secret: str = Field(default="dev-only-session-secret")
    api_key: str | None = None

    database_url: str = (
        "postgresql+asyncpg://money:money@db:5432/money"
    )

    llm_default_provider: str = "m1ultra"

    m1ultra_url: str = "http://host.docker.internal:11434"
    m1ultra_model: str = "jaahas/qwen3.5-uncensored:9b"
    m1ultra_timeout: int = 120
    m1ultra_embed_model: str = "nomic-embed-text"
    galaxy_one_api_key: str | None = None
    galaxy_one_endpoint: str = "https://llms.uat.galaxy.one/api/chat"
    galaxy_one_model: str = "mistral-cyber-mixlora:0.2311-q4km"
    galaxy_one_timeout: int = 120

    llm_allow_cloud: bool = False
    llm_cloud_monthly_budget_usd: float = 5.0
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-chat"
    deepseek_timeout: int = 60

    llm_agent_enabled: bool = True
    m1ultra_agent_model: str = "qwen3.5:9b"
    llm_agent_max_steps: int = 10
    llm_agent_timeout_sec: int = 60

    llm_gmail_tool_enabled: bool = False
    llm_gmail_tool_max_results: int = 10
    llm_gmail_tool_body_chars: int = 2000
    llm_gmail_rate_limit_hourly: int = 20

    langfuse_enabled: bool = False
    langfuse_host: str = "http://langfuse:3000"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None

    telegram_bot_token: str | None = None
    telegram_allowed_chat_ids: str = ""
    telegram_poll_interval_sec: int = 5

    gmail_target_email: str = "datnlqanalysts@gmail.com"
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/v1/oauth/google/callback"
    gmail_poll_interval_sec: int = 600
    # Comma-separated 24h-format hours (local tz) to run Gmail sync each day.
    # Default "8,20" = twice-a-day morning + evening. Set to empty "" to disable
    # the cron and fall back to interval (legacy noisy behaviour).
    gmail_sync_hours: str = "8,20"
    gmail_filter_senders: str = ""
    # When an email is successfully ingested (or was already ingested — dedup),
    # remove its UNREAD label so subsequent syncs skip it. Requires gmail.modify
    # scope — keep disabled if you only granted readonly.
    gmail_mark_read_after_ingest: bool = True
    # Fall back to LLM (m1ultra) when rule engine doesn't match an email.
    # Slower (30-60s/email) but much broader coverage.
    gmail_llm_fallback: bool = True
    # Skip LLM fallback for emails larger than this many body chars (avoid
    # big newsletters / marketing emails wasting tokens).
    gmail_llm_max_body_chars: int = 20000

    backup_retention_days: int = 30
    backup_age_pubkey: str | None = None

    @property
    def telegram_allowed_chat_ids_set(self) -> set[int]:
        return {
            int(x.strip()) for x in self.telegram_allowed_chat_ids.split(",") if x.strip().isdigit()
        }

    @property
    def gmail_filter_senders_list(self) -> list[str]:
        return [s.strip() for s in self.gmail_filter_senders.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
