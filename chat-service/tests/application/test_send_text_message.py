"""SendTextMessage — edge cases (Phase 2.2 refactor).

In Phase 2 the use case no longer invokes the LLM; it appends the
user's message and saves. LLM-driven concerns (multi-turn context,
LLM errors, ContextBuilder window) belong to StreamAssistantResponse
and are covered in ``test_stream_assistant_response.py`` (Phase 2.3).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from chat_service.application.use_cases.create_session import (
    CreateSessionCommand,
    CreateSessionHandler,
)
from chat_service.application.use_cases.send_text_message import (
    SendTextMessageCommand,
    SendTextMessageHandler,
)
from chat_service.domain.errors import SessionAlreadyTerminal, SessionNotFound
from chat_service.domain.value_objects.message_role import MessageRole
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.session_status import SessionStatus

from tests.conftest import InMemorySessionRepository


async def test_session_not_found_raises(
    repo: InMemorySessionRepository,
) -> None:
    handler = SendTextMessageHandler(sessions=repo)
    with pytest.raises(SessionNotFound):
        await handler.handle(SendTextMessageCommand(session_id=uuid4(), content="hi"))


async def test_returns_persisted_user_message(
    repo: InMemorySessionRepository, config: ModelConfig
) -> None:
    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(CreateSessionCommand(user_id=uuid4(), config=config))

    msg = await SendTextMessageHandler(sessions=repo).handle(
        SendTextMessageCommand(session_id=session.id, content="hi")
    )

    assert msg.role is MessageRole.USER
    assert msg.content == "hi"
    assert msg.seq == 1

    persisted = await repo.get(session.id)
    assert persisted is not None
    assert persisted.messages[-1] is msg


async def test_multiple_calls_increment_seq(
    repo: InMemorySessionRepository, config: ModelConfig
) -> None:
    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(CreateSessionCommand(user_id=uuid4(), config=config))
    handler = SendTextMessageHandler(sessions=repo)

    a = await handler.handle(SendTextMessageCommand(session_id=session.id, content="a"))
    b = await handler.handle(SendTextMessageCommand(session_id=session.id, content="b"))

    assert (a.seq, b.seq) == (1, 2)


async def test_terminal_session_cannot_accept_new_messages(
    repo: InMemorySessionRepository, config: ModelConfig
) -> None:
    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(CreateSessionCommand(user_id=uuid4(), config=config))
    session.transition_to(SessionStatus.ARCHIVED)
    await repo.save(session)

    handler = SendTextMessageHandler(sessions=repo)
    with pytest.raises(SessionAlreadyTerminal):
        await handler.handle(SendTextMessageCommand(session_id=session.id, content="hi"))
