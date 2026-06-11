"""Unit test: a blocking-read timeout is an idle poll, not a fault.

Uses a fake redis client (no container) so it runs in the normal suite.
"""

from __future__ import annotations

from typing import Any

from redis.exceptions import TimeoutError as RedisTimeoutError
from worker_service.infrastructure.streams.redis_stream_consumer import (
    RedisStreamConsumer,
)


class _TimeoutRedis:
    """xgroup_create succeeds; xreadgroup always times out."""

    async def xgroup_create(self, **_: Any) -> None:
        return None

    async def xreadgroup(self, **_: Any) -> Any:
        raise RedisTimeoutError("Timeout reading from 127.0.0.1:6379")


def _consumer(redis: Any) -> RedisStreamConsumer:
    return RedisStreamConsumer(redis=redis, stream="s", group="g", consumer_name="c")


async def test_read_timeout_returns_empty_batch() -> None:
    consumer = _consumer(_TimeoutRedis())
    assert await consumer.read(max_messages=10, block_ms=5000) == []
