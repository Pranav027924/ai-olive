"""SQLAlchemy ORM models for the logs schema (PRD §8.1).

Distinct from chat_service's models — the worker owns the logs
schema; chat-service owns the chat schema (same Postgres instance
during dev, separate DBs in production).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    DECIMAL,
    Integer,
    MetaData,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

LOGS_SCHEMA = "logs"


class Base(DeclarativeBase):
    metadata = MetaData(schema=LOGS_SCHEMA)


class InferenceLogRow(Base):
    """The hot table of every inference observation.

    ``id == LogEvent.event_id`` so the PK alone enforces idempotency
    — the worker treats a unique-violation as "already processed,
    ACK and move on" (PRD §10.4).
    """

    __tablename__ = "inference_logs"
    # SQLAlchemy ``mapped_column`` doesn't understand partitioning at the
    # ORM level — tests use the same migration via Alembic so we don't
    # need to teach ``metadata.create_all`` about RANGE here. Production
    # DDL lives in alembic/versions/0001_init_logs_schema.py.
    __table_args__ = {"schema": LOGS_SCHEMA}  # noqa: RUF012 — SQLAlchemy convention

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    message_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, primary_key=True
    )
    finished_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    ttft_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(DECIMAL(12, 6), nullable=True)
    raw_metadata: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    sdk_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class LogErrorRow(Base):
    __tablename__ = "log_errors"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    # Logical reference into inference_logs.id. No FK constraint because
    # inference_logs is partitioned by started_at and Postgres can't
    # enforce a single-column FK across the partition boundary (PRD §8.1
    # doesn't declare one either).
    log_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    error_type: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
