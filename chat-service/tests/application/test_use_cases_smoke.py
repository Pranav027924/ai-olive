"""Smoke tests for the chat-service use cases (Phase 1.4 + Phase 2.2).

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
from chat_service.application.use_cases.stream_assistant_response import (
    StreamAssistantResponseCommand,
    StreamAssistantResponseHandler,
    StreamChunk,
    StreamFinished,
    StreamStarted,
)
from chat_service.domain.value_objects.message_role import MessageRole
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.session_status import SessionStatus
from chat_service.domain.value_objects.streaming_response import StreamingState

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


async def test_send_text_message_appends_user_and_persists(
    repo: InMemorySessionRepository, config: ModelConfig
) -> None:
    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(CreateSessionCommand(user_id=uuid4(), config=config))

    user_msg = await SendTextMessageHandler(sessions=repo).handle(
        SendTextMessageCommand(session_id=session.id, content="hi there")
    )

    assert user_msg.role is MessageRole.USER
    assert user_msg.content == "hi there"
    assert user_msg.seq == 1

    persisted = await repo.get(session.id)
    assert persisted is not None
    assert [m.role for m in persisted.messages] == [MessageRole.USER]


async def test_stream_assistant_response_yields_started_chunks_finished(
    repo: InMemorySessionRepository, llm: FakeLLMClient, config: ModelConfig
) -> None:
    llm.chunks = ["hel", "lo ", "world"]

    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(CreateSessionCommand(user_id=uuid4(), config=config))
    await SendTextMessageHandler(sessions=repo).handle(
        SendTextMessageCommand(session_id=session.id, content="hi")
    )

    handler = StreamAssistantResponseHandler(sessions=repo, llm=llm)
    events = [
        e async for e in handler.handle(StreamAssistantResponseCommand(session_id=session.id))
    ]

    assert isinstance(events[0], StreamStarted)
    assert events[0].seq == 2  # user was seq=1
    chunks = [e for e in events if isinstance(e, StreamChunk)]
    assert [c.text for c in chunks] == ["hel", "lo ", "world"]
    finished = events[-1]
    assert isinstance(finished, StreamFinished)
    assert finished.state is StreamingState.COMPLETED
    assert finished.content == "hello world"
    assert finished.message.content == "hello world"
    assert finished.message.seq == 2

    persisted = await repo.get(session.id)
    assert persisted is not None
    assert [m.content for m in persisted.messages] == ["hi", "hello world"]
