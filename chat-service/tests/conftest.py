"""Shared pytest fixtures for the chat-service tests.

Provides the in-memory fakes that all application/HTTP tests reuse so
each test file doesn't redefine them. Production adapters arrive in
Phase 1.6 (Postgres) and Phase 1.8 (Anthropic LLM client).
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

import pytest
from chat_service.application.ports.llm_client import LLMClient
from chat_service.application.ports.session_repository import SessionRepository
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
    """Records inputs and returns a pre-set reply.

    Pass ``error=`` to make ``complete`` raise that exception.
    """

    def __init__(self, response: str = "ok", *, error: BaseException | None = None) -> None:
        self.response = response
        self.error = error
        self.call_count = 0
        self.received_messages: list[Message] | None = None
        self.received_config: ModelConfig | None = None
        self.received_system_prompt: str | None = None

    async def complete(
        self,
        *,
        messages: list[Message],
        config: ModelConfig,
        system_prompt: str | None = None,
    ) -> str:
        self.call_count += 1
        self.received_messages = list(messages)
        self.received_config = config
        self.received_system_prompt = system_prompt
        if self.error is not None:
            raise self.error
        return self.response


@pytest.fixture
def repo() -> InMemorySessionRepository:
    return InMemorySessionRepository()


@pytest.fixture
def llm() -> FakeLLMClient:
    return FakeLLMClient()


@pytest.fixture
def config() -> ModelConfig:
    return ModelConfig(provider="anthropic", model="claude-opus-4-7")
