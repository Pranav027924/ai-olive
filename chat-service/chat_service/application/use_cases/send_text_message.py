"""SendTextMessage — Phase 1 blocking command use case.

Appends the user's message, calls the LLM, appends the assistant's
reply, persists the session, and returns both new messages.

Streaming and cancellation arrive in Phase 2; this handler still
represents the canonical happy path even after that work lands.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from chat_service.application.ports.llm_client import LLMClient
from chat_service.application.ports.session_repository import SessionRepository
from chat_service.domain.entities.message import Message
from chat_service.domain.errors import SessionNotFound
from chat_service.domain.services.context_builder import ContextBuilder


@dataclass(frozen=True, slots=True)
class SendTextMessageCommand:
    session_id: UUID
    content: str


@dataclass(frozen=True, slots=True)
class SendTextMessageResult:
    user_message: Message
    assistant_message: Message


class SendTextMessageHandler:
    def __init__(
        self,
        *,
        sessions: SessionRepository,
        llm: LLMClient,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self._sessions = sessions
        self._llm = llm
        self._context_builder = context_builder or ContextBuilder()

    async def handle(self, cmd: SendTextMessageCommand) -> SendTextMessageResult:
        session = await self._sessions.get(cmd.session_id)
        if session is None:
            raise SessionNotFound(str(cmd.session_id))

        user_msg = session.add_user_message(cmd.content)

        context = self._context_builder.build(session)
        reply = await self._llm.complete(
            messages=context,
            config=session.config,
            system_prompt=session.system_prompt,
        )

        assistant_msg = session.add_assistant_message(reply)

        await self._sessions.save(session)
        return SendTextMessageResult(user_message=user_msg, assistant_message=assistant_msg)
