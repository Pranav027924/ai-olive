"""Integration tests for PostgresSessionRepository (Phase 1.7).

Each test runs against a real Postgres (via testcontainers). The
fixtures rebuild the ``chat`` schema between tests for isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from chat_service.domain.entities.session import Session
from chat_service.domain.value_objects.message_role import MessageRole
from chat_service.domain.value_objects.message_status import MessageStatus
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.session_status import SessionStatus
from chat_service.infrastructure.persistence.postgres_session_repo import (
    PostgresSessionRepository,
)


def _config() -> ModelConfig:
    return ModelConfig(provider="anthropic", model="claude-opus-4-7")


async def test_save_then_get_round_trips_full_aggregate(
    pg_repo: PostgresSessionRepository, dev_user_id: UUID
) -> None:
    session = Session.create(
        user_id=dev_user_id, config=_config(), title="hi", system_prompt="be brief"
    )
    session.add_user_message("question")
    session.add_assistant_message("answer")

    await pg_repo.save(session)

    fetched = await pg_repo.get(session.id)
    assert fetched is not None
    assert fetched.id == session.id
    assert fetched.user_id == dev_user_id
    assert fetched.title == "hi"
    assert fetched.system_prompt == "be brief"
    assert fetched.config == _config()
    assert fetched.status is SessionStatus.ACTIVE
    assert [(m.role, m.content, m.seq, m.status) for m in fetched.messages] == [
        (MessageRole.USER, "question", 1, MessageStatus.COMPLETE),
        (MessageRole.ASSISTANT, "answer", 2, MessageStatus.COMPLETE),
    ]


async def test_get_returns_none_for_unknown_id(
    pg_repo: PostgresSessionRepository, dev_user_id: UUID
) -> None:
    fetched = await pg_repo.get(UUID("00000000-0000-0000-0000-000000000099"))
    assert fetched is None


async def test_save_is_upsert_and_does_not_duplicate_existing_messages(
    pg_repo: PostgresSessionRepository, dev_user_id: UUID
) -> None:
    session = Session.create(user_id=dev_user_id, config=_config())
    session.add_user_message("first")
    await pg_repo.save(session)

    session.add_assistant_message("first reply")
    session.add_user_message("second")
    await pg_repo.save(session)

    fetched = await pg_repo.get(session.id)
    assert fetched is not None
    assert [m.content for m in fetched.messages] == ["first", "first reply", "second"]
    assert [m.seq for m in fetched.messages] == [1, 2, 3]


async def test_save_persists_status_transition(
    pg_repo: PostgresSessionRepository, dev_user_id: UUID
) -> None:
    session = Session.create(user_id=dev_user_id, config=_config())
    await pg_repo.save(session)

    session.transition_to(SessionStatus.COMPLETED)
    await pg_repo.save(session)

    fetched = await pg_repo.get(session.id)
    assert fetched is not None
    assert fetched.status is SessionStatus.COMPLETED


async def test_list_for_user_orders_by_updated_at_desc(
    pg_repo: PostgresSessionRepository, dev_user_id: UUID
) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    older = Session.create(user_id=dev_user_id, config=_config(), title="older", now=base)
    newer = Session.create(
        user_id=dev_user_id, config=_config(), title="newer", now=base + timedelta(hours=1)
    )
    await pg_repo.save(older)
    await pg_repo.save(newer)

    rows = await pg_repo.list_for_user(dev_user_id)

    assert [s.title for s in rows] == ["newer", "older"]


async def test_list_for_user_respects_status_filter(
    pg_repo: PostgresSessionRepository, dev_user_id: UUID
) -> None:
    active = Session.create(user_id=dev_user_id, config=_config(), title="a")
    completed = Session.create(user_id=dev_user_id, config=_config(), title="c")
    completed.transition_to(SessionStatus.COMPLETED)
    await pg_repo.save(active)
    await pg_repo.save(completed)

    completed_rows = await pg_repo.list_for_user(dev_user_id, status=SessionStatus.COMPLETED)

    assert len(completed_rows) == 1
    assert completed_rows[0].title == "c"


async def test_list_for_user_respects_limit_and_offset(
    pg_repo: PostgresSessionRepository, dev_user_id: UUID
) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(5):
        s = Session.create(
            user_id=dev_user_id, config=_config(), title=f"s{i}", now=base + timedelta(minutes=i)
        )
        await pg_repo.save(s)

    page1 = await pg_repo.list_for_user(dev_user_id, limit=2, offset=0)
    page2 = await pg_repo.list_for_user(dev_user_id, limit=2, offset=2)

    assert [s.title for s in page1] == ["s4", "s3"]
    assert [s.title for s in page2] == ["s2", "s1"]


async def test_user_isolation(
    pg_repo: PostgresSessionRepository, dev_user_id: UUID, fresh_user_id: UUID
) -> None:
    a = Session.create(user_id=dev_user_id, config=_config(), title="alice")
    b = Session.create(user_id=fresh_user_id, config=_config(), title="bob")
    await pg_repo.save(a)
    await pg_repo.save(b)

    alice_rows = await pg_repo.list_for_user(dev_user_id)
    bob_rows = await pg_repo.list_for_user(fresh_user_id)

    assert [s.title for s in alice_rows] == ["alice"]
    assert [s.title for s in bob_rows] == ["bob"]


async def test_duplicate_seq_within_session_is_rejected(
    pg_repo: PostgresSessionRepository, dev_user_id: UUID
) -> None:
    """The UNIQUE(session_id, seq) constraint is enforced at the DB level."""
    from chat_service.domain.entities.message import Message
    from sqlalchemy.exc import IntegrityError

    session = Session.create(user_id=dev_user_id, config=_config())
    session.add_user_message("a")  # seq=1
    await pg_repo.save(session)

    # Bypass the aggregate's monotonic-seq guard to force a collision.
    dup = Message(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        role=MessageRole.ASSISTANT,
        content="b",
        seq=1,  # collides with the user message above
        status=MessageStatus.COMPLETE,
        created_at=session.updated_at,
    )
    session.messages.append(dup)
    with pytest.raises(IntegrityError):
        await pg_repo.save(session)
