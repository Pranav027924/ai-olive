"""Integration tests for RedisCancellationStore (Phase 2.6).

Runs against a real Redis spun up by testcontainers (session-scoped;
each test starts from a flushed DB).
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from chat_service.infrastructure.cache.redis_cancellation_store import (
    CANCEL_KEY_PREFIX,
    RedisCancellationStore,
)
from redis.asyncio import Redis


async def test_mark_then_is_cancelled_returns_true(redis_client: Redis) -> None:
    store = RedisCancellationStore(redis=redis_client)
    sid = uuid4()

    await store.mark_cancelled(sid)

    assert await store.is_cancelled(sid) is True


async def test_unmarked_returns_false(redis_client: Redis) -> None:
    store = RedisCancellationStore(redis=redis_client)
    assert await store.is_cancelled(uuid4()) is False


async def test_clear_removes_flag(redis_client: Redis) -> None:
    store = RedisCancellationStore(redis=redis_client)
    sid = uuid4()

    await store.mark_cancelled(sid)
    await store.clear(sid)

    assert await store.is_cancelled(sid) is False


async def test_clear_is_idempotent_when_flag_absent(redis_client: Redis) -> None:
    store = RedisCancellationStore(redis=redis_client)
    await store.clear(uuid4())  # should not raise


async def test_mark_is_idempotent(redis_client: Redis) -> None:
    store = RedisCancellationStore(redis=redis_client)
    sid = uuid4()
    await store.mark_cancelled(sid)
    await store.mark_cancelled(sid)
    assert await store.is_cancelled(sid) is True


async def test_per_session_isolation(redis_client: Redis) -> None:
    store = RedisCancellationStore(redis=redis_client)
    a, b = uuid4(), uuid4()

    await store.mark_cancelled(a)

    assert await store.is_cancelled(a) is True
    assert await store.is_cancelled(b) is False


async def test_ttl_is_set_on_mark(redis_client: Redis) -> None:
    """The cancel key has a TTL within the configured window."""
    store = RedisCancellationStore(redis=redis_client, ttl_seconds=120)
    sid = uuid4()
    await store.mark_cancelled(sid)

    ttl = await redis_client.ttl(f"{CANCEL_KEY_PREFIX}{sid}")
    assert 0 < ttl <= 120


async def test_short_ttl_expires_flag(redis_client: Redis) -> None:
    """End-to-end: a short TTL really does expire the key.

    Uses a 1-second TTL to keep the test fast. We sleep slightly
    longer to be robust to coarse Redis clock granularity.
    """
    store = RedisCancellationStore(redis=redis_client, ttl_seconds=1)
    sid = uuid4()
    await store.mark_cancelled(sid)
    assert await store.is_cancelled(sid) is True

    await asyncio.sleep(1.5)

    assert await store.is_cancelled(sid) is False
