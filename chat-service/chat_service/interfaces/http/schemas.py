"""Pydantic request/response models for the chat-service HTTP API.

These are *wire* models, distinct from the domain entities. The
router code translates between them and the domain.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from chat_service.domain.entities.session import Session

Provider = Literal["openai", "anthropic", "gemini", "deepseek"]


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    system_prompt: str | None = None
    provider: Provider = "anthropic"
    model: str = "claude-opus-4-7"


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)


class MessageView(BaseModel):
    id: UUID
    role: str
    content: str
    seq: int
    status: str
    created_at: datetime


class SessionView(BaseModel):
    id: UUID
    user_id: UUID
    title: str | None
    system_prompt: str | None
    provider: str
    model: str
    status: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageView]

    @classmethod
    def from_domain(cls, session: Session) -> SessionView:
        return cls(
            id=session.id,
            user_id=session.user_id,
            title=session.title,
            system_prompt=session.system_prompt,
            provider=session.config.provider,
            model=session.config.model,
            status=session.status.value,
            created_at=session.created_at,
            updated_at=session.updated_at,
            messages=[
                MessageView(
                    id=m.id,
                    role=m.role.value,
                    content=m.content,
                    seq=m.seq,
                    status=m.status.value,
                    created_at=m.created_at,
                )
                for m in session.messages
            ],
        )


class SendMessageResponse(BaseModel):
    user_message: MessageView
    assistant_message: MessageView


class ProblemDetail(BaseModel):
    """RFC 7807 problem details (PRD §9.6)."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
