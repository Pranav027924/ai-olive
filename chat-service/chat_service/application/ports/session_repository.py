"""SessionRepository — outbound port for session persistence.

The application layer depends on this Protocol. Concrete adapters
(Postgres via SQLAlchemy in Phase 1.6, in-memory in tests) implement
it. Domain never touches it directly.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from chat_service.domain.entities.session import Session
from chat_service.domain.value_objects.session_status import SessionStatus


class SessionRepository(Protocol):
    """Async port for loading and persisting :class:`Session` aggregates."""

    async def get(self, session_id: UUID) -> Session | None:
        """Return the session with ``session_id`` or ``None`` if absent."""

    async def save(self, session: Session) -> None:
        """Upsert the session (and its messages) atomically."""

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        status: SessionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Session]:
        """List sessions for ``user_id``, newest first, optionally status-filtered."""
