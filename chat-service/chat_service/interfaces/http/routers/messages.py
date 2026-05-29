"""Messages router — blocking send (Phase 1).

Streaming variant arrives in Phase 2.7.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from chat_service.application.use_cases.send_text_message import SendTextMessageCommand
from chat_service.domain.entities.message import Message
from chat_service.interfaces.http.dependencies import SendTextMessageDep
from chat_service.interfaces.http.schemas import (
    MessageView,
    SendMessageRequest,
    SendMessageResponse,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/{session_id}/messages",
    response_model=SendMessageResponse,
    status_code=status.HTTP_200_OK,
)
async def send_text_message(
    session_id: UUID,
    body: SendMessageRequest,
    handler: SendTextMessageDep,
) -> SendMessageResponse:
    result = await handler.handle(
        SendTextMessageCommand(session_id=session_id, content=body.content)
    )
    return SendMessageResponse(
        user_message=_view(result.user_message),
        assistant_message=_view(result.assistant_message),
    )


def _view(msg: Message) -> MessageView:
    return MessageView(
        id=msg.id,
        role=msg.role.value,
        content=msg.content,
        seq=msg.seq,
        status=msg.status.value,
        created_at=msg.created_at,
    )
