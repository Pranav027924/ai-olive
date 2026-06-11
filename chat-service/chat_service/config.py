"""Chat-service settings.

Pydantic ``BaseSettings`` reads from environment variables (or the
``.env`` file at the repo root during local dev). The ``CHAT_`` prefix
keeps service settings disjoint from sibling services that share the
same .env (PRD §9.1).
"""

from __future__ import annotations

from pathlib import Path
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

    # ---- LLM (used in Phase 1.8; multi-provider in Phase 7.3) ----
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    deepseek_api_key: str = ""
    default_provider: str = "anthropic"
    default_model: str = "claude-opus-4-7"

    @property
    def provider_api_keys(self) -> dict[str, str]:
        return {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "gemini": self.gemini_api_key,
            "deepseek": self.deepseek_api_key,
        }

    # ---- Behaviour ----
    context_window: int = Field(default=20, ge=1, le=200)
    cancel_ttl_seconds: int = Field(default=600, ge=10, le=86400)

    # ---- Logging SDK ----
    log_emitter_path: Path = Path("logs") / "inference.jsonl"

    # HTTP emitter (Phase 4.10). When ingestion_url is empty the
    # chat-service falls back to file-only emission so dev without an
    # ingestion service still gets local JSONL output.
    ingestion_url: str = ""
    ingestion_api_key: str = ""
    http_emitter_max_batch: int = Field(default=20, ge=1, le=1000)
    http_emitter_flush_interval_seconds: float = Field(default=2.0, gt=0.0)
    http_emitter_queue_size: int = Field(default=1000, ge=1)

    # ---- Object storage (PRD §6.7) ----
    s3_bucket: str = "olive-attachments"
    s3_endpoint_url: str = "http://127.0.0.1:9000"
    s3_access_key: str = "olive_dev_access"
    s3_secret_key: str = "olive_dev_secret"  # noqa: S105 — local dev default
    s3_region: str = "us-east-1"

    # ---- Transcription (PRD §6.6) ----
    whisper_model_size: str = "tiny"

    # ---- Auth (PRD §9.4) ----
    # JWT is HS256 with a shared secret. ``disable_auth`` keeps the dev
    # user-id shim so local dev, the UI, and the test suite work without
    # minting tokens. Production MUST set DISABLE_AUTH=false + JWT_SECRET.
    disable_auth: bool = True
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_audience: str = ""
    jwt_issuer: str = ""
    jwt_ttl_minutes: int = Field(default=60 * 24 * 7, ge=1)  # 7 days
    allow_registration: bool = True
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
