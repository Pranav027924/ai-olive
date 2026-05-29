"""StreamConsumer — outbound port for Redis Streams reads (PRD §6.4, §7.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StreamMessage:
    """One stream entry: the Redis-Streams message id + raw payload dict."""

    message_id: str
    payload: dict[str, str]


class StreamConsumer(Protocol):
    async def read(self, *, max_messages: int, block_ms: int) -> list[StreamMessage]:
        """Block up to ``block_ms`` waiting for at most ``max_messages``."""

    async def ack(self, message_ids: list[str]) -> None:
        """Acknowledge that processing is complete; messages won't be redelivered."""
