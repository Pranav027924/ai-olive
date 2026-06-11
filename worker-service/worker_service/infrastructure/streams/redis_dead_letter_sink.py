"""RedisDeadLetterSink — XADD poison messages to a DLQ stream (PRD §9.6).

Re-publishes the original payload plus diagnostic fields (the failure
reason, the source message id, and a UTC timestamp) onto a dedicated
``inference_logs_dlq`` stream. Trimmed with an approximate MAXLEN so
the DLQ can't grow without bound.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from redis.asyncio import Redis

from worker_service.application.ports.dead_letter_sink import DeadLetterSink
from worker_service.application.ports.stream_consumer import StreamMessage


class RedisDeadLetterSink(DeadLetterSink):
    def __init__(self, *, redis: Redis, stream: str, maxlen: int = 100_000) -> None:
        self._redis = redis
        self._stream = stream
        self._maxlen = maxlen

    async def send(self, message: StreamMessage, *, reason: str) -> None:
        entry: dict[str, str] = {
            **message.payload,
            "dlq_reason": reason,
            "dlq_source_id": message.message_id,
            "dlq_at": datetime.now(tz=UTC).isoformat(),
        }
        # redis-py widens the field mapping type on both sides; we only
        # ever pass {str: str}, so the cast is the price of staying typed.
        await self._redis.xadd(
            self._stream,
            cast("dict[Any, Any]", entry),
            maxlen=self._maxlen,
            approximate=True,
        )
