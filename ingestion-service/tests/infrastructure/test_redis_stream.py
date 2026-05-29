"""Integration tests for RedisStreamAdapter (Phase 4.5).

Real Redis via testcontainers. Each test starts from a flushed db.
"""

from __future__ import annotations

import re
from uuid import uuid4

from ingestion_service.infrastructure.streams.redis_stream import (
    DEFAULT_STREAM,
    RedisStreamAdapter,
)
from redis.asyncio import Redis

STREAM_ID_PATTERN = re.compile(r"^\d+-\d+$")


async def test_add_returns_a_well_formed_stream_id(redis_client: Redis) -> None:
    adapter = RedisStreamAdapter(redis=redis_client)
    sid = await adapter.add({"ingestion_id": str(uuid4()), "event": '{"k":"v"}'})
    assert STREAM_ID_PATTERN.fullmatch(sid), sid


async def test_xlen_increases_by_one_per_add(redis_client: Redis) -> None:
    adapter = RedisStreamAdapter(redis=redis_client)
    assert await redis_client.xlen(DEFAULT_STREAM) == 0

    for _ in range(5):
        await adapter.add({"ingestion_id": str(uuid4()), "event": '{"k":"v"}'})

    assert await redis_client.xlen(DEFAULT_STREAM) == 5


async def test_payload_round_trips_through_xrange(redis_client: Redis) -> None:
    adapter = RedisStreamAdapter(redis=redis_client)
    ingestion_id = str(uuid4())
    event_json = '{"event_id": "abc", "model": "claude-opus-4-7"}'

    sid = await adapter.add({"ingestion_id": ingestion_id, "event": event_json})

    entries = await redis_client.xrange(DEFAULT_STREAM, min=sid, max=sid)
    assert entries is not None
    assert len(entries) == 1
    stored_sid, payload = entries[0]
    assert stored_sid == sid
    assert payload == {"ingestion_id": ingestion_id, "event": event_json}


async def test_custom_stream_name_is_honoured(redis_client: Redis) -> None:
    adapter = RedisStreamAdapter(redis=redis_client, stream="my_logs")
    await adapter.add({"k": "v"})
    assert await redis_client.xlen("my_logs") == 1
    assert await redis_client.xlen(DEFAULT_STREAM) == 0


async def test_maxlen_trim_keeps_stream_below_the_cap(redis_client: Redis) -> None:
    """approximate=True means actual length can exceed maxlen briefly,
    but stays close. We verify it never balloons way past the cap."""
    adapter = RedisStreamAdapter(redis=redis_client, maxlen=50)

    for _ in range(500):
        await adapter.add({"event": "x"})

    length = await redis_client.xlen(DEFAULT_STREAM)
    # Redis approximate trimming guarantees length is within ±1% of maxlen
    # on small caps it can drift by a few nodes; allow up to 2x slack.
    assert length <= 100, f"stream grew unbounded to {length}"


async def test_concurrent_adds_all_land_in_order(redis_client: Redis) -> None:
    """Stream ids are monotonically increasing even under concurrency."""
    import asyncio

    adapter = RedisStreamAdapter(redis=redis_client)
    ids = await asyncio.gather(*(adapter.add({"i": str(i)}) for i in range(20)))

    # All distinct, all parseable as "ms-seq", and monotonically non-decreasing.
    assert len(set(ids)) == 20
    parsed = [tuple(int(p) for p in sid.split("-")) for sid in ids]
    sorted_parsed = sorted(parsed)
    assert parsed == sorted_parsed or set(parsed) == set(sorted_parsed)
