"""CancelStream — command use case for the POST /chat/{id}/cancel endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from chat_service.application.ports.cancellation_store import CancellationStore
from chat_service.application.ports.session_repository import SessionRepository
from chat_service.domain.errors import SessionNotFound


@dataclass(frozen=True, slots=True)
class CancelStreamCommand:
    session_id: UUID


class CancelStreamHandler:
    def __init__(self, *, sessions: SessionRepository, cancellations: CancellationStore) -> None:
        self._sessions = sessions
        self._cancellations = cancellations

    async def handle(self, cmd: CancelStreamCommand) -> None:
        # Verify the session exists so an unknown id returns 404 rather
        # than silently flipping a flag for a nonexistent session.
        session = await self._sessions.get(cmd.session_id)
        if session is None:
            raise SessionNotFound(str(cmd.session_id))
        await self._cancellations.mark_cancelled(cmd.session_id)
