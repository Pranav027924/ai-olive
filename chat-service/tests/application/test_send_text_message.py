"""SendTextMessage — not-found, errors, context (Phase 1.5)."""

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
from chat_service.domain.services.context_builder import ContextBuilder
from chat_service.domain.value_objects.message_role import MessageRole
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.session_status import SessionStatus

from tests.conftest import FakeLLMClient, InMemorySessionRepository


async def test_session_not_found_raises(
    repo: InMemorySessionRepository, llm: FakeLLMClient
) -> None:
    handler = SendTextMessageHandler(sessions=repo, llm=llm)

    with pytest.raises(SessionNotFound):
        await handler.handle(SendTextMessageCommand(session_id=uuid4(), content="hi"))

    # LLM was never called on a not-found path.
    assert llm.call_count == 0


async def test_llm_error_propagates_and_session_is_not_saved_with_assistant(
    repo: InMemorySessionRepository, config: ModelConfig
) -> None:
    """An LLM failure aborts the use case; the user message is in memory but
    persistence does not happen (the use case saves once, at the very end)."""
    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(CreateSessionCommand(user_id=uuid4(), config=config))

    boom = RuntimeError("provider on fire")
    llm = FakeLLMClient(error=boom)

    handler = SendTextMessageHandler(sessions=repo, llm=llm)
    with pytest.raises(RuntimeError, match="provider on fire"):
        await handler.handle(SendTextMessageCommand(session_id=session.id, content="hi"))

    # No assistant turn was written, but the user message that the handler
    # appended *before* the LLM call IS visible on the in-memory aggregate
    # because save() was never reached (the same Session instance is stored
    # by ref in the in-memory repo). This documents current behaviour and
    # locks it in until the optional rollback in §1.9 is in place.
    persisted = await repo.get(session.id)
    assert persisted is not None
    assert [m.role for m in persisted.messages] == [MessageRole.USER]


async def test_multi_turn_includes_previous_context(
    repo: InMemorySessionRepository, llm: FakeLLMClient, config: ModelConfig
) -> None:
    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(CreateSessionCommand(user_id=uuid4(), config=config))
    handler = SendTextMessageHandler(sessions=repo, llm=llm)

    llm.response = "first reply"
    await handler.handle(SendTextMessageCommand(session_id=session.id, content="first"))

    llm.response = "second reply"
    await handler.handle(SendTextMessageCommand(session_id=session.id, content="second"))

    # The LLM's second call should see all 3 prior turns (first user, first
    # assistant, second user). The handler appends the user message before
    # building context, so the context includes it.
    assert llm.received_messages is not None
    assert [m.role for m in llm.received_messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.USER,
    ]
    assert [m.content for m in llm.received_messages] == ["first", "first reply", "second"]


async def test_terminal_session_cannot_accept_new_messages(
    repo: InMemorySessionRepository, llm: FakeLLMClient, config: ModelConfig
) -> None:
    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(CreateSessionCommand(user_id=uuid4(), config=config))
    session.transition_to(SessionStatus.ARCHIVED)
    await repo.save(session)

    handler = SendTextMessageHandler(sessions=repo, llm=llm)
    with pytest.raises(SessionAlreadyTerminal):
        await handler.handle(SendTextMessageCommand(session_id=session.id, content="hi"))

    assert llm.call_count == 0


async def test_context_builder_window_is_respected(
    repo: InMemorySessionRepository, llm: FakeLLMClient, config: ModelConfig
) -> None:
    """A small window only passes the last K messages to the LLM."""
    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(CreateSessionCommand(user_id=uuid4(), config=config))

    # Pre-populate 5 prior turns then send a new one with window=2.
    for i in range(5):
        session.add_user_message(f"u{i}")
        session.add_assistant_message(f"a{i}")
    await repo.save(session)

    handler = SendTextMessageHandler(
        sessions=repo, llm=llm, context_builder=ContextBuilder(window=2)
    )
    await handler.handle(SendTextMessageCommand(session_id=session.id, content="new"))

    # Window=2 over messages including the freshly-appended "new" yields the
    # last assistant turn and the new user turn.
    assert llm.received_messages is not None
    assert [m.content for m in llm.received_messages] == ["a4", "new"]
