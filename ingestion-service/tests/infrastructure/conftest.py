"""Fixtures for ingestion-service infrastructure tests.

Spins up a real Redis via testcontainers (session-scoped — one
container per pytest run). Each test gets a flushed DB.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:7-alpine") as r:
        yield r


@pytest_asyncio.fixture
async def redis_client(redis_container: RedisContainer) -> AsyncIterator[Redis]:
    url = (
        f"redis://{redis_container.get_container_host_ip()}:"
        f"{redis_container.get_exposed_port(6379)}/0"
    )
    client: Redis = Redis.from_url(url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.aclose()
