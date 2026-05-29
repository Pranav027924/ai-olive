"""RedisStreamAdapter — implements the LogStream port (PRD §6.3, §7.3).

XADDs each event payload to a single Redis Stream
(``inference_logs`` by default) with approximate MAXLEN trimming so
the stream is bounded even when the worker falls behind.

Trim mode notes:
- ``approximate=True`` (Redis' ``MAXLEN ~`` form) lets Redis trim on
  whole stream nodes rather than exact length — much cheaper, and
  the actual length stays within ±1% of ``stream_maxlen`` which is
  fine for an analytics buffer.
"""

from __future__ import annotations

from typing import Any, cast

from redis.asyncio import Redis

from ingestion_service.application.ports.log_stream import LogStream

DEFAULT_STREAM = "inference_logs"
DEFAULT_MAXLEN = 1_000_000


class RedisStreamAdapter(LogStream):
    def __init__(
        self,
        *,
        redis: Redis,
        stream: str = DEFAULT_STREAM,
        maxlen: int = DEFAULT_MAXLEN,
    ) -> None:
        self._redis = redis
        self._stream = stream
        self._maxlen = maxlen

    async def add(self, payload: dict[str, str]) -> str:
        # redis-py's xadd parameter type widens to bytes|str on both sides;
        # we only ever pass {str: str} so the cast is the price of staying
        # mypy-strict without retyping the upstream signature.
        message_id = await self._redis.xadd(
            self._stream,
            cast("dict[Any, Any]", payload),
            maxlen=self._maxlen,
            approximate=True,
        )
        return message_id if isinstance(message_id, str) else message_id.decode()
