"""init logs schema (inference_logs partitioned + log_errors)

Revision ID: 0001
Revises:
Create Date: 2026-05-29

PRD §8.1. The composite PK (id, started_at) on inference_logs is the
minimum Postgres requires for a partitioned table — the partition key
must be part of the PK. Idempotency is still by event_id because the
SDK uses one started_at per event_id.

Single catch-all partition 2026-2030 keeps Phase 5 unblocked; monthly
partitions arrive in a later migration via pg_partman or a cron.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS logs")

    # Parent partitioned table.
    op.execute(
        """
        CREATE TABLE logs.inference_logs (
            id UUID NOT NULL,
            session_id UUID NOT NULL,
            message_id UUID,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ NOT NULL,
            latency_ms INT NOT NULL,
            ttft_ms INT,
            prompt_tokens INT,
            completion_tokens INT,
            input_preview TEXT,
            output_preview TEXT,
            cost_usd NUMERIC(12,6),
            raw_metadata JSONB,
            sdk_version TEXT,
            ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, started_at)
        ) PARTITION BY RANGE (started_at);
        """
    )

    # Single catch-all partition for 2026..2030.
    op.execute(
        """
        CREATE TABLE logs.inference_logs_p_catchall
        PARTITION OF logs.inference_logs
        FOR VALUES FROM ('2026-01-01') TO ('2030-01-01');
        """
    )

    op.create_index(
        "ix_inference_logs_session_started_desc",
        "inference_logs",
        ["session_id", sa.text("started_at DESC")],
        schema="logs",
    )
    op.create_index(
        "ix_inference_logs_model_started_desc",
        "inference_logs",
        ["model", sa.text("started_at DESC")],
        schema="logs",
    )
    op.create_index(
        "ix_inference_logs_status_started_desc_nonsuccess",
        "inference_logs",
        ["status", sa.text("started_at DESC")],
        schema="logs",
        postgresql_where=sa.text("status != 'success'"),
    )

    # Errors side-table — no FK because the parent is partitioned and
    # Postgres can't enforce a single-column FK to a partitioned table.
    op.create_table(
        "log_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("log_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("error_type", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="logs",
    )
    op.create_index(
        "ix_log_errors_log_id",
        "log_errors",
        ["log_id"],
        schema="logs",
    )


def downgrade() -> None:
    op.drop_index("ix_log_errors_log_id", table_name="log_errors", schema="logs")
    op.drop_table("log_errors", schema="logs")
    op.drop_index(
        "ix_inference_logs_status_started_desc_nonsuccess",
        table_name="inference_logs",
        schema="logs",
    )
    op.drop_index(
        "ix_inference_logs_model_started_desc",
        table_name="inference_logs",
        schema="logs",
    )
    op.drop_index(
        "ix_inference_logs_session_started_desc",
        table_name="inference_logs",
        schema="logs",
    )
    op.execute("DROP TABLE IF EXISTS logs.inference_logs CASCADE")
    op.execute("DROP SCHEMA IF EXISTS logs")
