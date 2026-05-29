"""Ingestion-service settings (PRD §9.1).

Reads environment variables (case-insensitive) and the repo-root
``.env`` during local dev. Same naming convention as chat-service so
``POSTGRES_*`` / ``REDIS_*`` env vars are shared across services.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Redis ----
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0

    # ---- Stream (PRD §7.3) ----
    stream_name: str = "inference_logs"
    stream_maxlen: int = Field(default=1_000_000, ge=1)

    # ---- HTTP ----
    http_host: str = "127.0.0.1"
    http_port: int = 8001

    # ---- Auth (PRD §9.5) ----
    ingestion_api_key: str = ""

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
