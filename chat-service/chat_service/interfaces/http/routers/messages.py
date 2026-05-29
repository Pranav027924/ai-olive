"""Messages router.

In Phase 2 ``POST /chat/{id}/messages`` only appends the user message
to the session and returns it as a 201. The assistant reply arrives
via the SSE endpoint at ``GET /chat/{id}/stream`` (added in 2.7).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from chat_service.application.use_cases.send_text_message import SendTextMessageCommand
from chat_service.domain.entities.message import Message
from chat_service.interfaces.http.dependencies import SendTextMessageDep
from chat_service.interfaces.http.schemas import MessageView, SendMessageRequest

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/{session_id}/messages",
    response_model=MessageView,
    status_code=status.HTTP_201_CREATED,
)
async def send_text_message(
    session_id: UUID,
    body: SendMessageRequest,
    handler: SendTextMessageDep,
) -> MessageView:
    msg = await handler.handle(SendTextMessageCommand(session_id=session_id, content=body.content))
    return _view(msg)


def _view(msg: Message) -> MessageView:
    return MessageView(
        id=msg.id,
        role=msg.role.value,
        content=msg.content,
        seq=msg.seq,
        status=msg.status.value,
        created_at=msg.created_at,
    )
