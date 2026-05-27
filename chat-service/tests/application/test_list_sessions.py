"""ListSessions — pagination, filtering, isolation (Phase 1.5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from chat_service.application.use_cases.list_sessions import (
    ListSessionsHandler,
    ListSessionsQuery,
)
from chat_service.domain.entities.session import Session
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.session_status import SessionStatus

from tests.conftest import InMemorySessionRepository


def _seed_sessions(
    *,
    user_id: object,
    count: int,
    config: ModelConfig,
    start: datetime,
    status: SessionStatus = SessionStatus.ACTIVE,
) -> list[Session]:
    """Create ``count`` sessions for ``user_id`` with strictly increasing updated_at."""
    sessions: list[Session] = []
    for i in range(count):
        s = Session.create(
            user_id=user_id,  # type: ignore[arg-type]
            config=config,
            title=f"s{i}",
            now=start + timedelta(minutes=i),
        )
        if status is not SessionStatus.ACTIVE:
            s.transition_to(status, now=start + timedelta(minutes=i))
        sessions.append(s)
    return sessions


async def test_empty_repo_returns_empty_list(
    repo: InMemorySessionRepository,
) -> None:
    rows = await ListSessionsHandler(sessions=repo).handle(ListSessionsQuery(user_id=uuid4()))
    assert rows == []


async def test_ordering_is_updated_at_descending(
    repo: InMemorySessionRepository, config: ModelConfig
) -> None:
    user_id = uuid4()
    seeded = _seed_sessions(
        user_id=user_id, count=3, config=config, start=datetime(2026, 1, 1, tzinfo=UTC)
    )
    repo.seed(seeded)

    rows = await ListSessionsHandler(sessions=repo).handle(ListSessionsQuery(user_id=user_id))

    # Seeded with strictly increasing updated_at; expected order is reverse.
    assert [s.title for s in rows] == ["s2", "s1", "s0"]


async def test_pagination_respects_limit_and_offset(
    repo: InMemorySessionRepository, config: ModelConfig
) -> None:
    user_id = uuid4()
    repo.seed(
        _seed_sessions(
            user_id=user_id, count=5, config=config, start=datetime(2026, 1, 1, tzinfo=UTC)
        )
    )

    handler = ListSessionsHandler(sessions=repo)

    first_page = await handler.handle(ListSessionsQuery(user_id=user_id, limit=2, offset=0))
    second_page = await handler.handle(ListSessionsQuery(user_id=user_id, limit=2, offset=2))

    assert [s.title for s in first_page] == ["s4", "s3"]
    assert [s.title for s in second_page] == ["s2", "s1"]


async def test_status_filter_only_returns_matching_sessions(
    repo: InMemorySessionRepository, config: ModelConfig
) -> None:
    user_id = uuid4()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    repo.seed(_seed_sessions(user_id=user_id, count=2, config=config, start=start))
    repo.seed(
        _seed_sessions(
            user_id=user_id,
            count=2,
            config=config,
            start=start + timedelta(hours=1),
            status=SessionStatus.COMPLETED,
        )
    )

    handler = ListSessionsHandler(sessions=repo)
    completed = await handler.handle(
        ListSessionsQuery(user_id=user_id, status=SessionStatus.COMPLETED)
    )

    assert len(completed) == 2
    assert all(s.status is SessionStatus.COMPLETED for s in completed)


async def test_user_isolation(repo: InMemorySessionRepository, config: ModelConfig) -> None:
    alice = uuid4()
    bob = uuid4()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    repo.seed(_seed_sessions(user_id=alice, count=3, config=config, start=start))
    repo.seed(_seed_sessions(user_id=bob, count=2, config=config, start=start))

    handler = ListSessionsHandler(sessions=repo)
    alice_rows = await handler.handle(ListSessionsQuery(user_id=alice))
    bob_rows = await handler.handle(ListSessionsQuery(user_id=bob))

    assert len(alice_rows) == 3
    assert len(bob_rows) == 2
    assert all(s.user_id == alice for s in alice_rows)
    assert all(s.user_id == bob for s in bob_rows)
