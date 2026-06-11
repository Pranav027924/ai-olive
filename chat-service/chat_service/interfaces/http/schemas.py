"""Pydantic request/response models for the chat-service HTTP API.

These are *wire* models, distinct from the domain entities. The
router code translates between them and the domain.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from chat_service.domain.entities.attachment import Attachment
from chat_service.domain.entities.session import Session
from chat_service.domain.entities.user import User

Provider = Literal["openai", "anthropic", "gemini", "deepseek"]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class AuthUserView(BaseModel):
    id: UUID
    email: str

    @classmethod
    def from_domain(cls, user: User) -> AuthUserView:
        return cls(id=user.id, email=user.email)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 — OAuth token type label, not a secret
    user: AuthUserView


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


class AttachmentView(BaseModel):
    id: UUID
    session_id: UUID
    kind: str
    filename: str
    mime_type: str
    size_bytes: int
    parse_status: str
    parsed_text: str | None
    transcript: str | None
    created_at: datetime

    @classmethod
    def from_domain(cls, attachment: Attachment) -> AttachmentView:
        return cls(
            id=attachment.id,
            session_id=attachment.session_id,
            kind=attachment.kind.value,
            filename=attachment.filename,
            mime_type=attachment.mime_type,
            size_bytes=attachment.size_bytes,
            parse_status=attachment.parse_status.value,
            parsed_text=attachment.parsed_text,
            transcript=attachment.transcript,
            created_at=attachment.created_at,
        )


class ProblemDetail(BaseModel):
    """RFC 7807 problem details (PRD §9.6)."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
