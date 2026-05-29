"""StreamAssistantResponse — async-generator use case (PRD Phase 2.2).

The handler is itself an async generator. It yields one of three
event types so the HTTP layer can frame an SSE stream without having
to inspect domain state:

    StreamStarted   first event; carries the pre-generated assistant
                    message_id and its seq so clients can correlate
                    later updates without waiting for completion.
    StreamChunk     each successive delta produced by the LLM.
    StreamFinished  always the last event; carries the terminal
                    StreamingState (COMPLETED / CANCELLED / ERRORED),
                    the final accumulated content, and the persisted
                    Message. Even on LLM failure the message is saved
                    (with status=ERROR) and StreamFinished is yielded;
                    the use case does not re-raise.

Cancellation arrives in Phase 2.5; this handler is unconditional for
now and always finishes COMPLETED (or ERRORED on LLM failure).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

from chat_service.application.ports.llm_client import LLMClient
from chat_service.application.ports.session_repository import SessionRepository
from chat_service.domain.entities.message import Message
from chat_service.domain.errors import SessionAlreadyTerminal, SessionNotFound
from chat_service.domain.services.context_builder import ContextBuilder
from chat_service.domain.value_objects.message_status import MessageStatus
from chat_service.domain.value_objects.streaming_response import (
    StreamingResponse,
    StreamingState,
)


@dataclass(frozen=True, slots=True)
class StreamAssistantResponseCommand:
    session_id: UUID


@dataclass(frozen=True, slots=True)
class StreamStarted:
    assistant_message_id: UUID
    seq: int


@dataclass(frozen=True, slots=True)
class StreamChunk:
    text: str


@dataclass(frozen=True, slots=True)
class StreamFinished:
    state: StreamingState
    content: str
    message: Message
    error: str | None = None


StreamEvent = StreamStarted | StreamChunk | StreamFinished


def _msg_status_for(state: StreamingState) -> MessageStatus:
    return {
        StreamingState.COMPLETED: MessageStatus.COMPLETE,
        StreamingState.CANCELLED: MessageStatus.CANCELLED,
        StreamingState.ERRORED: MessageStatus.ERROR,
        # ACTIVE should never reach here, but be defensive
        StreamingState.ACTIVE: MessageStatus.ERROR,
    }[state]


class StreamAssistantResponseHandler:
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

    async def handle(self, cmd: StreamAssistantResponseCommand) -> AsyncIterator[StreamEvent]:
        session = await self._sessions.get(cmd.session_id)
        if session is None:
            raise SessionNotFound(str(cmd.session_id))
        # Fail fast on terminal sessions — otherwise the caller would see
        # StreamStarted + chunks before add_assistant_message raised at the end.
        if session.status.is_terminal:
            raise SessionAlreadyTerminal(session.status)

        assistant_msg_id = uuid4()
        next_seq = len(session.messages) + 1

        yield StreamStarted(assistant_message_id=assistant_msg_id, seq=next_seq)

        stream = StreamingResponse(session_id=session.id, message_id=assistant_msg_id)
        context = self._context_builder.build(session)

        error_detail: str | None = None
        try:
            async for chunk in self._llm.stream(
                messages=context,
                config=session.config,
                system_prompt=session.system_prompt,
            ):
                stream.push(chunk)
                yield StreamChunk(text=chunk)
            stream.complete()
        except Exception as exc:
            stream.error()
            error_detail = f"{type(exc).__name__}: {exc}"

        msg = session.add_assistant_message(
            content=stream.content,
            message_id=assistant_msg_id,
            status=_msg_status_for(stream.state),
        )
        await self._sessions.save(session)

        yield StreamFinished(
            state=stream.state,
            content=stream.content,
            message=msg,
            error=error_detail,
        )
