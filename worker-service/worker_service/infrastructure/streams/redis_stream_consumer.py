"""RedisStreamConsumer — concrete StreamConsumer over Redis Streams (PRD §6.4).

Uses an XREADGROUP loop with a consumer group so the worker can be
horizontally scaled later — each worker instance picks up a subset of
messages. ``ensure_group`` creates the group on first use; subsequent
calls are idempotent.
"""

from __future__ import annotations

from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from worker_service.application.ports.stream_consumer import (
    StreamConsumer,
    StreamMessage,
)


class RedisStreamConsumer(StreamConsumer):
    def __init__(
        self,
        *,
        redis: Redis,
        stream: str,
        group: str,
        consumer_name: str,
    ) -> None:
        self._redis = redis
        self._stream = stream
        self._group = group
        self._consumer_name = consumer_name
        self._group_created = False

    async def ensure_group(self) -> None:
        """Create the consumer group if it doesn't already exist.

        Uses ``MKSTREAM`` so the call works even when no event has
        landed yet — ``$`` means "deliver only messages added after
        group creation", which matches the worker's at-least-once
        semantics.
        """
        if self._group_created:
            return
        try:
            await self._redis.xgroup_create(
                name=self._stream,
                groupname=self._group,
                id="$",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self._group_created = True

    async def read(self, *, max_messages: int, block_ms: int) -> list[StreamMessage]:
        await self.ensure_group()
        response = await self._redis.xreadgroup(
            groupname=self._group,
            consumername=self._consumer_name,
            streams={self._stream: ">"},
            count=max_messages,
            block=block_ms,
        )
        return _flatten(response)

    async def ack(self, message_ids: list[str]) -> None:
        if not message_ids:
            return
        await self._redis.xack(self._stream, self._group, *message_ids)


def _flatten(response: Any) -> list[StreamMessage]:
    """Convert redis-py's nested response into a flat StreamMessage list."""
    if not response:
        return []
    messages: list[StreamMessage] = []
    for _stream_name, entries in response:
        for raw_id, payload in entries:
            message_id = raw_id if isinstance(raw_id, str) else raw_id.decode()
            messages.append(
                StreamMessage(
                    message_id=message_id,
                    payload=cast("dict[str, str]", payload),
                )
            )
    return messages
