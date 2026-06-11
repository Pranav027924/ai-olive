"""Worker-service settings (PRD §9.1).

Reads environment variables (case-insensitive) and the repo-root
``.env`` during local dev. Shares POSTGRES_* / REDIS_* conventions
with chat-service and ingestion-service.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
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
    postgres_password: str = "olive_dev_pw"  # noqa: S105 — local default; real value comes from .env
    postgres_db: str = "olive"

    # ---- Redis ----
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0

    # ---- Stream (PRD §7.3) ----
    stream_name: str = "inference_logs"
    consumer_group: str = "log_processors"
    consumer_name: str = "worker-1"

    # ---- Dead-letter queue (PRD §9.6) ----
    dlq_stream_name: str = "inference_logs_dlq"
    dlq_maxlen: int = Field(default=100_000, ge=1)

    # ---- ClickHouse analytics sink (PRD §7.5) ----
    clickhouse_url: str = "http://127.0.0.1:8123"
    clickhouse_user: str = "olive"
    clickhouse_password: str = "olive_dev_pw_ch"  # noqa: S105 — local default
    clickhouse_db: str = "olive"
    clickhouse_buffer_size: int = Field(default=50, ge=1)
    clickhouse_flush_interval_seconds: float = Field(default=3.0, gt=0.0)

    # ---- Worker loop ----
    batch_size: int = Field(default=10, ge=1, le=1000)
    poll_block_ms: int = Field(default=5000, ge=100, le=60000)

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
