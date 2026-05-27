"""ListSessions — query use case."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from chat_service.application.ports.session_repository import SessionRepository
from chat_service.domain.entities.session import Session
from chat_service.domain.value_objects.session_status import SessionStatus


@dataclass(frozen=True, slots=True)
class ListSessionsQuery:
    user_id: UUID
    status: SessionStatus | None = None
    limit: int = 50
    offset: int = 0


class ListSessionsHandler:
    def __init__(self, *, sessions: SessionRepository) -> None:
        self._sessions = sessions

    async def handle(self, query: ListSessionsQuery) -> list[Session]:
        return await self._sessions.list_for_user(
            query.user_id,
            status=query.status,
            limit=query.limit,
            offset=query.offset,
        )
