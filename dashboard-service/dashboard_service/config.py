"""Dashboard-service settings (PRD §7.7)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class DashboardServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- ClickHouse ----
    clickhouse_url: str = "http://127.0.0.1:8123"
    clickhouse_user: str = "olive"
    clickhouse_password: str = "olive_dev_pw_ch"  # noqa: S105 — local dev default
    clickhouse_db: str = "olive"
    clickhouse_table: str = "inference_metrics"
