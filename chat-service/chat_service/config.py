"""Chat-service settings.

Pydantic ``BaseSettings`` reads from environment variables (or the
``.env`` file at the repo root during local dev). The ``CHAT_`` prefix
keeps service settings disjoint from sibling services that share the
same .env (PRD §9.1).
"""

from __future__ import annotations

from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChatServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Postgres ----
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_user: str = "olive"
    postgres_password: str = "olive_dev_pw"  # noqa: S105 — local dev default; real value comes from .env
    postgres_db: str = "olive"

    # ---- Redis ----
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0

    # ---- LLM (used in Phase 1.8) ----
    anthropic_api_key: str = ""
    default_provider: str = "anthropic"
    default_model: str = "claude-opus-4-7"

    # ---- Behaviour ----
    context_window: int = Field(default=20, ge=1, le=200)
    cancel_ttl_seconds: int = Field(default=600, ge=10, le=86400)

    # ---- Dev-only auth shim until JWT lands in Phase 9.4 ----
    dev_user_id: UUID = UUID("00000000-0000-0000-0000-000000000001")
    dev_user_email: str = "dev@local"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
