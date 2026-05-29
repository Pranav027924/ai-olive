"""Tests for CancelStreamHandler (Phase 2.5)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from chat_service.application.use_cases.cancel_stream import (
    CancelStreamCommand,
    CancelStreamHandler,
)
from chat_service.application.use_cases.create_session import (
    CreateSessionCommand,
    CreateSessionHandler,
)
from chat_service.domain.errors import SessionNotFound
from chat_service.domain.value_objects.model_config import ModelConfig

from tests.conftest import InMemoryCancellationStore, InMemorySessionRepository


async def test_marks_session_cancelled(
    repo: InMemorySessionRepository,
    cancellations: InMemoryCancellationStore,
    config: ModelConfig,
) -> None:
    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(CreateSessionCommand(user_id=uuid4(), config=config))

    handler = CancelStreamHandler(sessions=repo, cancellations=cancellations)
    await handler.handle(CancelStreamCommand(session_id=session.id))

    assert await cancellations.is_cancelled(session.id) is True
    assert cancellations.mark_calls == [session.id]


async def test_session_not_found_raises_without_marking(
    repo: InMemorySessionRepository, cancellations: InMemoryCancellationStore
) -> None:
    handler = CancelStreamHandler(sessions=repo, cancellations=cancellations)
    unknown = uuid4()

    with pytest.raises(SessionNotFound):
        await handler.handle(CancelStreamCommand(session_id=unknown))

    assert cancellations.mark_calls == []


async def test_mark_is_idempotent(
    repo: InMemorySessionRepository,
    cancellations: InMemoryCancellationStore,
    config: ModelConfig,
) -> None:
    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(CreateSessionCommand(user_id=uuid4(), config=config))

    handler = CancelStreamHandler(sessions=repo, cancellations=cancellations)
    await handler.handle(CancelStreamCommand(session_id=session.id))
    await handler.handle(CancelStreamCommand(session_id=session.id))

    assert await cancellations.is_cancelled(session.id) is True
    assert cancellations.mark_calls == [session.id, session.id]
