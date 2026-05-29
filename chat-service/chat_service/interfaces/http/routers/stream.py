"""SSE streaming endpoint + cancel endpoint (PRD §6.1, Phase 2.7).

GET /chat/{session_id}/stream
- Pre-flight checks (session exists + non-terminal) so 404 / 409 come
  back as plain problem+json before the SSE response opens.
- Returns ``text/event-stream`` framed by sse-starlette.
- Event types:
    event: started   data: {"message_id": "...", "seq": N}
    event: chunk     data: {"text": "..."}
    event: finished  data: {"state": "...", "content": "...",
                            "message_id": "...", "error": null|"..."}

POST /chat/{session_id}/cancel
- Sets the cancel flag in the CancellationStore. The in-flight
  streaming handler polls between LLM tokens and stops with
  state=CANCELLED.
- 204 No Content on success, 404 problem+json if the session
  doesn't exist.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, status
from sse_starlette.sse import EventSourceResponse

from chat_service.application.use_cases.cancel_stream import CancelStreamCommand
from chat_service.application.use_cases.stream_assistant_response import (
    StreamAssistantResponseCommand,
    StreamChunk,
    StreamFinished,
    StreamStarted,
)
from chat_service.domain.errors import SessionAlreadyTerminal, SessionNotFound
from chat_service.interfaces.http.dependencies import (
    CancelStreamDep,
    RepoDep,
    StreamAssistantResponseDep,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/{session_id}/stream")
async def stream(
    session_id: UUID,
    repo: RepoDep,
    handler: StreamAssistantResponseDep,
) -> EventSourceResponse:
    # Pre-flight: 404 / 409 should be conventional HTTP problem+json,
    # not mid-stream SSE events. Domain exceptions trigger the app-level
    # handlers registered in app.py.
    session = await repo.get(session_id)
    if session is None:
        raise SessionNotFound(str(session_id))
    if session.status.is_terminal:
        raise SessionAlreadyTerminal(session.status)

    async def event_gen() -> AsyncIterator[dict[str, str]]:
        async for event in handler.handle(StreamAssistantResponseCommand(session_id=session_id)):
            if isinstance(event, StreamStarted):
                yield {
                    "event": "started",
                    "data": json.dumps(
                        {"message_id": str(event.assistant_message_id), "seq": event.seq}
                    ),
                }
            elif isinstance(event, StreamChunk):
                yield {"event": "chunk", "data": json.dumps({"text": event.text})}
            elif isinstance(event, StreamFinished):
                yield {
                    "event": "finished",
                    "data": json.dumps(
                        {
                            "state": event.state.value,
                            "content": event.content,
                            "message_id": str(event.message.id),
                            "error": event.error,
                        }
                    ),
                }

    return EventSourceResponse(event_gen())


@router.post("/{session_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel(session_id: UUID, handler: CancelStreamDep) -> None:
    await handler.handle(CancelStreamCommand(session_id=session_id))
