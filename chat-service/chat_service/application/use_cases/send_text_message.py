"""SendTextMessage — Phase 2 user-only command use case.

Appends the user's message to the session and saves. The assistant
reply is generated separately by :class:`StreamAssistantResponseHandler`
(invoked from the SSE streaming endpoint introduced in Phase 2.7).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from chat_service.application.ports.session_repository import SessionRepository
from chat_service.domain.entities.message import Message
from chat_service.domain.errors import SessionNotFound


@dataclass(frozen=True, slots=True)
class SendTextMessageCommand:
    session_id: UUID
    content: str


class SendTextMessageHandler:
    def __init__(self, *, sessions: SessionRepository) -> None:
        self._sessions = sessions

    async def handle(self, cmd: SendTextMessageCommand) -> Message:
        session = await self._sessions.get(cmd.session_id)
        if session is None:
            raise SessionNotFound(str(cmd.session_id))

        msg = session.add_user_message(cmd.content)
        await self._sessions.save(session)
        return msg
