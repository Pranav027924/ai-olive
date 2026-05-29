"""init chat schema (users, sessions, messages) + seed dev user

Revision ID: 0001
Revises:
Create Date: 2026-05-27

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
DEV_USER_EMAIL = "dev@local"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS chat")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        schema="chat",
    )

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["chat.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('active','cancelled','completed','archived','deleted')",
            name="sessions_status_check",
        ),
        schema="chat",
    )
    op.create_index(
        "ix_sessions_user_updated",
        "sessions",
        ["user_id", "updated_at"],
        schema="chat",
        postgresql_where=sa.text("status != 'deleted'"),
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat.sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "seq", name="messages_session_seq_uq"),
        sa.CheckConstraint(
            "role IN ('user','assistant','system','tool')",
            name="messages_role_check",
        ),
        sa.CheckConstraint(
            "status IN ('pending','complete','cancelled','error')",
            name="messages_status_check",
        ),
        schema="chat",
    )
    op.create_index(
        "ix_messages_session_seq",
        "messages",
        ["session_id", "seq"],
        schema="chat",
    )

    # Seed the dev user — keeps the HTTP layer (Phase 1.9) FK-valid until
    # JWT auth lands in Phase 9.4. Idempotent via ON CONFLICT.
    op.execute(
        sa.text(
            "INSERT INTO chat.users (id, email) VALUES (CAST(:uid AS uuid), :email) "
            "ON CONFLICT (id) DO NOTHING"
        ).bindparams(uid=DEV_USER_ID, email=DEV_USER_EMAIL)
    )


def downgrade() -> None:
    op.drop_index("ix_messages_session_seq", table_name="messages", schema="chat")
    op.drop_table("messages", schema="chat")
    op.drop_index("ix_sessions_user_updated", table_name="sessions", schema="chat")
    op.drop_table("sessions", schema="chat")
    op.drop_table("users", schema="chat")
    op.execute("DROP SCHEMA IF EXISTS chat")
