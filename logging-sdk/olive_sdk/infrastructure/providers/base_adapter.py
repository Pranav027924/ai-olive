"""ProviderAdapter — base port + provider-event types (Phase 3.4).

PRD §6.2: each adapter normalises a provider's API into a uniform
async generator yielding ``chunk`` and ``usage`` events. Phase 3.4
ships the Anthropic adapter; OpenAI / Gemini / DeepSeek land in
Phase 7.1.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

ChatRole = Literal["user", "assistant", "system"]


@dataclass(frozen=True, slots=True)
class ChatTurn:
    """Provider-neutral chat message in the order it should be sent."""

    role: ChatRole
    content: str


@dataclass(frozen=True, slots=True)
class ChunkEvent:
    """A delta of the assistant's text reply."""

    text: str


@dataclass(frozen=True, slots=True)
class UsageEvent:
    """Token-usage totals reported by the provider after the stream ends."""

    prompt_tokens: int
    completion_tokens: int


ProviderEvent = ChunkEvent | UsageEvent


class ProviderAdapter(Protocol):
    """Streams the assistant reply and ends with a single UsageEvent."""

    def stream(
        self,
        *,
        model: str,
        messages: list[ChatTurn],
        system_prompt: str | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        """Yield ChunkEvents in order, then exactly one UsageEvent at the end."""
