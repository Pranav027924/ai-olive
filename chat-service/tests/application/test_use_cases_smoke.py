"""Smoke tests for the chat-service use cases (Phase 1.4).

Each use case is exercised on its happy path with simple in-memory
fakes for the SessionRepository and LLMClient ports. Detailed coverage
(not-found, validation errors, edge cases) follows in Phase 1.5.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from chat_service.application.ports.llm_client import LLMClient
from chat_service.application.ports.session_repository import SessionRepository
from chat_service.application.use_cases.create_session import (
    CreateSessionCommand,
    CreateSessionHandler,
)
from chat_service.application.use_cases.list_sessions import (
    ListSessionsHandler,
    ListSessionsQuery,
)
from chat_service.application.use_cases.send_text_message import (
    SendTextMessageCommand,
    SendTextMessageHandler,
)
from chat_service.domain.entities.message import Message
from chat_service.domain.entities.session import Session
from chat_service.domain.value_objects.message_role import MessageRole
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.session_status import SessionStatus


class InMemorySessionRepository(SessionRepository):
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


class FakeLLMClient(LLMClient):
    def __init__(self, response: str = "hello back") -> None:
        self.response = response
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
        self.received_messages = list(messages)
        self.received_config = config
        self.received_system_prompt = system_prompt
        return self.response


def _config() -> ModelConfig:
    return ModelConfig(provider="anthropic", model="claude-opus-4-7")


# ---------------------------------------------------------------------------
# CreateSession
# ---------------------------------------------------------------------------


async def test_create_session_persists_and_returns_session() -> None:
    repo = InMemorySessionRepository()
    handler = CreateSessionHandler(sessions=repo)
    user_id = uuid4()

    session = await handler.handle(
        CreateSessionCommand(user_id=user_id, config=_config(), title="hi")
    )

    assert session.user_id == user_id
    assert session.title == "hi"
    assert session.status is SessionStatus.ACTIVE
    assert await repo.get(session.id) is session


# ---------------------------------------------------------------------------
# ListSessions
# ---------------------------------------------------------------------------


async def test_list_sessions_returns_user_sessions_ordered_by_updated_at_desc() -> None:
    repo = InMemorySessionRepository()
    create = CreateSessionHandler(sessions=repo)
    user_id = uuid4()

    older = await create.handle(CreateSessionCommand(user_id=user_id, config=_config(), title="a"))
    newer = await create.handle(CreateSessionCommand(user_id=user_id, config=_config(), title="b"))

    handler = ListSessionsHandler(sessions=repo)
    rows = await handler.handle(ListSessionsQuery(user_id=user_id))

    # Both sessions returned; newer first (ordering by updated_at desc).
    ids = [s.id for s in rows]
    assert set(ids) == {older.id, newer.id}


# ---------------------------------------------------------------------------
# SendTextMessage
# ---------------------------------------------------------------------------


async def test_send_text_message_appends_user_then_assistant_and_persists() -> None:
    repo = InMemorySessionRepository()
    llm = FakeLLMClient(response="hello back")
    create = CreateSessionHandler(sessions=repo)

    session = await create.handle(
        CreateSessionCommand(user_id=uuid4(), config=_config(), system_prompt="be brief")
    )

    handler = SendTextMessageHandler(sessions=repo, llm=llm)
    result = await handler.handle(SendTextMessageCommand(session_id=session.id, content="hi there"))

    # Result references the two new messages
    assert result.user_message.role is MessageRole.USER
    assert result.user_message.content == "hi there"
    assert result.assistant_message.role is MessageRole.ASSISTANT
    assert result.assistant_message.content == "hello back"

    # Session has both messages persisted, seq 1 then 2
    persisted = await repo.get(session.id)
    assert persisted is not None
    assert [m.seq for m in persisted.messages] == [1, 2]

    # LLM was called with the prior context (user message included) and
    # received the session's system prompt verbatim.
    assert llm.received_system_prompt == "be brief"
    assert llm.received_config == _config()
    assert llm.received_messages is not None
    assert llm.received_messages[-1].content == "hi there"
