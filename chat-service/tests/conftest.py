"""Shared pytest fixtures for the chat-service tests.

Provides the in-memory fakes that all application/HTTP tests reuse so
each test file doesn't redefine them. Production adapters arrive in
Phase 1.6 (Postgres) and Phase 1.8 (Anthropic LLM client).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from uuid import UUID

import pytest
from chat_service.application.ports.attachment_repository import AttachmentRepository
from chat_service.application.ports.cancellation_store import CancellationStore
from chat_service.application.ports.llm_client import LLMClient
from chat_service.application.ports.session_repository import SessionRepository
from chat_service.domain.entities.attachment import Attachment
from chat_service.domain.entities.message import Message
from chat_service.domain.entities.session import Session
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.session_status import SessionStatus


class InMemorySessionRepository(SessionRepository):
    """Mutable, ordered, single-process. Suitable for unit tests only."""

    def __init__(self) -> None:
        self._store: dict[UUID, Session] = {}

    async def get(self, session_id: UUID) -> Session | None:
        return self._store.get(session_id)

    async def save(self, session: Session) -> None:
        self._store[session.id] = session

    async def delete(self, session_id: UUID) -> None:
        self._store.pop(session_id, None)

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        status: SessionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Session]:
        rows = [s for s in self._store.values() if s.user_id == user_id]
        if status is not None:
            rows = [s for s in rows if s.status is status]
        rows.sort(key=lambda s: s.updated_at, reverse=True)
        return rows[offset : offset + limit]

    # Helpers for tests
    def seed(self, sessions: Iterable[Session]) -> None:
        for s in sessions:
            self._store[s.id] = s


class FakeLLMClient(LLMClient):
    """Records inputs and yields a pre-set reply as chunks.

    Pass ``chunks=["foo", "bar"]`` to control deltas explicitly, or
    ``response="foobar"`` to yield it as a single chunk.

    Pass ``error=`` to raise that exception after the chunks (or
    immediately if no chunks are provided) — useful for testing the
    StreamFinished(state=ERRORED) path.
    """

    def __init__(
        self,
        response: str = "ok",
        *,
        chunks: list[str] | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.response = response
        self.chunks = chunks
        self.error = error
        self.call_count = 0
        self.received_session_id: UUID | None = None
        self.received_message_id: UUID | None = None
        self.received_messages: list[Message] | None = None
        self.received_config: ModelConfig | None = None
        self.received_system_prompt: str | None = None

    async def stream(
        self,
        *,
        session_id: UUID,
        message_id: UUID | None,
        messages: list[Message],
        config: ModelConfig,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        self.call_count += 1
        self.received_session_id = session_id
        self.received_message_id = message_id
        self.received_messages = list(messages)
        self.received_config = config
        self.received_system_prompt = system_prompt
        chunks = self.chunks if self.chunks is not None else [self.response]
        for chunk in chunks:
            yield chunk
        if self.error is not None:
            raise self.error


class InMemoryCancellationStore(CancellationStore):
    """Simple set-backed cancellation store for unit tests.

    Phase 2.6 ships the production Redis adapter; tests that don't
    need the cancel path use the NoOp default baked into
    StreamAssistantResponseHandler.
    """

    def __init__(self) -> None:
        self._flagged: set[UUID] = set()
        self.mark_calls: list[UUID] = []
        self.is_cancelled_calls: list[UUID] = []
        self.clear_calls: list[UUID] = []

    async def mark_cancelled(self, session_id: UUID) -> None:
        self._flagged.add(session_id)
        self.mark_calls.append(session_id)

    async def is_cancelled(self, session_id: UUID) -> bool:
        self.is_cancelled_calls.append(session_id)
        return session_id in self._flagged

    async def clear(self, session_id: UUID) -> None:
        self._flagged.discard(session_id)
        self.clear_calls.append(session_id)


class InMemoryAttachmentRepository(AttachmentRepository):
    def __init__(self) -> None:
        self._store: dict[UUID, Attachment] = {}

    async def get(self, attachment_id: UUID) -> Attachment | None:
        return self._store.get(attachment_id)

    async def list_for_session(self, session_id: UUID) -> list[Attachment]:
        rows = [a for a in self._store.values() if a.session_id == session_id]
        rows.sort(key=lambda a: a.created_at)
        return rows

    async def save(self, attachment: Attachment) -> None:
        self._store[attachment.id] = attachment


@pytest.fixture
def repo() -> InMemorySessionRepository:
    return InMemorySessionRepository()


@pytest.fixture
def attachments() -> InMemoryAttachmentRepository:
    return InMemoryAttachmentRepository()


@pytest.fixture
def llm() -> FakeLLMClient:
    return FakeLLMClient()


@pytest.fixture
def cancellations() -> InMemoryCancellationStore:
    return InMemoryCancellationStore()


@pytest.fixture
def config() -> ModelConfig:
    return ModelConfig(provider="anthropic", model="claude-opus-4-7")
