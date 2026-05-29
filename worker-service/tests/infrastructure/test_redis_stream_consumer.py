"""Integration tests for RedisStreamConsumer (Phase 5.9)."""

from __future__ import annotations

from redis.asyncio import Redis
from worker_service.infrastructure.streams.redis_stream_consumer import (
    RedisStreamConsumer,
)

STREAM = "inference_logs"
GROUP = "log_processors"


def _make(consumer: str = "worker-1", *, redis: Redis) -> RedisStreamConsumer:
    return RedisStreamConsumer(
        redis=redis,
        stream=STREAM,
        group=GROUP,
        consumer_name=consumer,
    )


async def test_ensure_group_creates_the_group_when_absent(
    redis_client: Redis,
) -> None:
    consumer = _make(redis=redis_client)
    await consumer.ensure_group()

    info = await redis_client.xinfo_groups(STREAM)
    names = [g["name"] for g in info]
    assert GROUP in names


async def test_ensure_group_is_idempotent(redis_client: Redis) -> None:
    consumer = _make(redis=redis_client)
    await consumer.ensure_group()
    # Second call should not raise (BUSYGROUP).
    await consumer.ensure_group()

    info = await redis_client.xinfo_groups(STREAM)
    assert len(info) == 1


async def test_produce_then_consume_returns_payload(redis_client: Redis) -> None:
    consumer = _make(redis=redis_client)
    await consumer.ensure_group()

    sid = await redis_client.xadd(STREAM, {"ingestion_id": "abc", "event": '{"k":"v"}'})

    messages = await consumer.read(max_messages=10, block_ms=200)
    assert len(messages) == 1
    msg = messages[0]
    assert msg.message_id == sid
    assert msg.payload == {"ingestion_id": "abc", "event": '{"k":"v"}'}


async def test_consume_no_messages_returns_empty_list(redis_client: Redis) -> None:
    consumer = _make(redis=redis_client)
    await consumer.ensure_group()
    messages = await consumer.read(max_messages=10, block_ms=50)
    assert messages == []


async def test_ack_marks_message_processed(redis_client: Redis) -> None:
    consumer = _make(redis=redis_client)
    await consumer.ensure_group()

    sid = await redis_client.xadd(STREAM, {"k": "v"})
    messages = await consumer.read(max_messages=10, block_ms=200)
    assert [m.message_id for m in messages] == [str(sid)]

    await consumer.ack([str(sid)])

    info = await redis_client.xinfo_groups(STREAM)
    assert info[0]["pending"] == 0


async def test_unacked_messages_redeliver_via_pending(
    redis_client: Redis,
) -> None:
    """Messages read but not acked stay pending; a second consumer in the
    same group can claim them via XPENDING / XCLAIM, but a fresh ``>``
    read returns only NEW messages."""
    consumer = _make("worker-1", redis=redis_client)
    await consumer.ensure_group()

    sid_a = await redis_client.xadd(STREAM, {"i": "a"})
    sid_b = await redis_client.xadd(STREAM, {"i": "b"})

    first = await consumer.read(max_messages=10, block_ms=100)
    assert {m.message_id for m in first} == {sid_a, sid_b}
    # Both are now PEL.
    info = await redis_client.xinfo_groups(STREAM)
    assert info[0]["pending"] == 2

    # A second ``>`` read returns nothing because no NEW messages are
    # available.
    second = await consumer.read(max_messages=10, block_ms=50)
    assert second == []


async def test_max_messages_caps_one_read(redis_client: Redis) -> None:
    consumer = _make(redis=redis_client)
    await consumer.ensure_group()

    for i in range(5):
        await redis_client.xadd(STREAM, {"i": str(i)})

    first = await consumer.read(max_messages=2, block_ms=200)
    assert len(first) == 2
    # The next read picks up the remaining three.
    second = await consumer.read(max_messages=10, block_ms=200)
    assert len(second) == 3
