"""UserRepository — outbound port for account persistence (PRD §9.4)."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from chat_service.domain.entities.user import User


class UserRepository(Protocol):
    async def get_by_email(self, email: str) -> User | None:
        """Return the user with this email, or ``None``."""

    async def get(self, user_id: UUID) -> User | None:
        """Return the user with this id, or ``None``."""

    async def create(self, user: User) -> None:
        """Insert a new user row."""
