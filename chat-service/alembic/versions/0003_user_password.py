"""chat.users.password_hash

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-11

PRD §9.4. Adds a nullable bcrypt password hash to users so the chat
service can register + authenticate accounts and mint JWTs. Nullable
so pre-existing rows (e.g. the dev user) keep working under
DISABLE_AUTH.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_hash", sa.Text(), nullable=True),
        schema="chat",
    )


def downgrade() -> None:
    op.drop_column("users", "password_hash", schema="chat")
