"""RedisCancellationStore — Redis-backed adapter for CancellationStore (Phase 2.6).

Stores one ``cancel:{session_id}`` key per session with a TTL
(``cancel_ttl_seconds`` in settings, default 600s). The TTL is a
safety net so a stale flag can't haunt a session that's resumed
much later — long enough to outlive any reasonable streaming
response, short enough that we never see a flag from "yesterday".
"""

from __future__ import annotations

from uuid import UUID

from redis.asyncio import Redis

from chat_service.application.ports.cancellation_store import CancellationStore

CANCEL_KEY_PREFIX = "cancel:"


class RedisCancellationStore(CancellationStore):
    def __init__(self, *, redis: Redis, ttl_seconds: int = 600) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def mark_cancelled(self, session_id: UUID) -> None:
        await self._redis.set(self._key(session_id), "1", ex=self._ttl)

    async def is_cancelled(self, session_id: UUID) -> bool:
        value = await self._redis.get(self._key(session_id))
        return value is not None

    async def clear(self, session_id: UUID) -> None:
        await self._redis.delete(self._key(session_id))

    @staticmethod
    def _key(session_id: UUID) -> str:
        return f"{CANCEL_KEY_PREFIX}{session_id}"
