"""CreateSession — edge-case coverage (Phase 1.5)."""

from __future__ import annotations

from uuid import uuid4

from chat_service.application.use_cases.create_session import (
    CreateSessionCommand,
    CreateSessionHandler,
)
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.session_status import SessionStatus

from tests.conftest import InMemorySessionRepository


async def test_two_sessions_for_same_user_get_distinct_ids(
    repo: InMemorySessionRepository, config: ModelConfig
) -> None:
    handler = CreateSessionHandler(sessions=repo)
    user_id = uuid4()

    a = await handler.handle(CreateSessionCommand(user_id=user_id, config=config))
    b = await handler.handle(CreateSessionCommand(user_id=user_id, config=config))

    assert a.id != b.id


async def test_sessions_belong_to_their_respective_users(
    repo: InMemorySessionRepository, config: ModelConfig
) -> None:
    handler = CreateSessionHandler(sessions=repo)
    alice = uuid4()
    bob = uuid4()

    a = await handler.handle(CreateSessionCommand(user_id=alice, config=config))
    b = await handler.handle(CreateSessionCommand(user_id=bob, config=config))

    assert (await repo.get(a.id)).user_id == alice  # type: ignore[union-attr]
    assert (await repo.get(b.id)).user_id == bob  # type: ignore[union-attr]


async def test_title_and_system_prompt_are_optional(
    repo: InMemorySessionRepository, config: ModelConfig
) -> None:
    handler = CreateSessionHandler(sessions=repo)

    session = await handler.handle(CreateSessionCommand(user_id=uuid4(), config=config))

    assert session.title is None
    assert session.system_prompt is None
    assert session.status is SessionStatus.ACTIVE


async def test_system_prompt_is_preserved_verbatim(
    repo: InMemorySessionRepository, config: ModelConfig
) -> None:
    handler = CreateSessionHandler(sessions=repo)
    prompt = "You are a concise assistant. Reply in fewer than 50 words."

    session = await handler.handle(
        CreateSessionCommand(user_id=uuid4(), config=config, system_prompt=prompt)
    )

    assert session.system_prompt == prompt


async def test_provider_and_model_are_taken_from_command(
    repo: InMemorySessionRepository,
) -> None:
    handler = CreateSessionHandler(sessions=repo)
    cfg = ModelConfig(provider="openai", model="gpt-4o")

    session = await handler.handle(CreateSessionCommand(user_id=uuid4(), config=cfg))

    assert session.config == cfg
