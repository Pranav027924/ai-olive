"""chat.attachments

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-04

PRD §8.1. Attachments belong to a chat session and optionally to a
specific message. The blob lives in object storage (s3_key); parsed
text / transcript columns are populated by media-service after the
background parsing job completes.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("parse_status", sa.Text(), nullable=False),
        sa.Column("parsed_text", sa.Text(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["chat.sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["chat.messages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "kind IN ('file','audio','image')",
            name="attachments_kind_check",
        ),
        sa.CheckConstraint(
            "parse_status IN ('pending','complete','failed')",
            name="attachments_parse_status_check",
        ),
        schema="chat",
    )
    op.create_index(
        "ix_attachments_session_created",
        "attachments",
        ["session_id", sa.text("created_at DESC")],
        schema="chat",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_attachments_session_created",
        table_name="attachments",
        schema="chat",
    )
    op.drop_table("attachments", schema="chat")
