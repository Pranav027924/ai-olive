"""Smoke tests for the chat-service use cases (Phase 1.4).

Each use case is exercised on its happy path. Edge cases live in the
per-use-case files alongside this one.
"""

from __future__ import annotations

from uuid import uuid4

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
from chat_service.domain.value_objects.message_role import MessageRole
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.session_status import SessionStatus

from tests.conftest import FakeLLMClient, InMemorySessionRepository


async def test_create_session_persists_and_returns_session(
    repo: InMemorySessionRepository, config: ModelConfig
) -> None:
    handler = CreateSessionHandler(sessions=repo)
    user_id = uuid4()

    session = await handler.handle(CreateSessionCommand(user_id=user_id, config=config, title="hi"))

    assert session.user_id == user_id
    assert session.title == "hi"
    assert session.status is SessionStatus.ACTIVE
    assert await repo.get(session.id) is session


async def test_list_sessions_returns_user_sessions(
    repo: InMemorySessionRepository, config: ModelConfig
) -> None:
    create = CreateSessionHandler(sessions=repo)
    user_id = uuid4()
    a = await create.handle(CreateSessionCommand(user_id=user_id, config=config, title="a"))
    b = await create.handle(CreateSessionCommand(user_id=user_id, config=config, title="b"))

    rows = await ListSessionsHandler(sessions=repo).handle(ListSessionsQuery(user_id=user_id))

    assert {s.id for s in rows} == {a.id, b.id}


async def test_send_text_message_appends_user_then_assistant_and_persists(
    repo: InMemorySessionRepository, llm: FakeLLMClient, config: ModelConfig
) -> None:
    llm.response = "hello back"
    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(
        CreateSessionCommand(user_id=uuid4(), config=config, system_prompt="be brief")
    )

    result = await SendTextMessageHandler(sessions=repo, llm=llm).handle(
        SendTextMessageCommand(session_id=session.id, content="hi there")
    )

    assert result.user_message.role is MessageRole.USER
    assert result.user_message.content == "hi there"
    assert result.assistant_message.role is MessageRole.ASSISTANT
    assert result.assistant_message.content == "hello back"

    persisted = await repo.get(session.id)
    assert persisted is not None
    assert [m.seq for m in persisted.messages] == [1, 2]

    assert llm.received_system_prompt == "be brief"
    assert llm.received_config == config
    assert llm.received_messages is not None
    assert llm.received_messages[-1].content == "hi there"
