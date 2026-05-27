"""LLMClient — outbound port for calling an LLM provider.

The application layer depends on this Protocol. In Phase 1 a direct
Anthropic adapter implements it (1.8). In Phase 3.10 the adapter is
replaced by one that wraps the logging SDK. The Protocol itself
should not change.
"""

from __future__ import annotations

from typing import Protocol

from chat_service.domain.entities.message import Message
from chat_service.domain.value_objects.model_config import ModelConfig


class LLMClient(Protocol):
    """Async port for blocking LLM completions (streaming arrives in Phase 2)."""

    async def complete(
        self,
        *,
        messages: list[Message],
        config: ModelConfig,
        system_prompt: str | None = None,
    ) -> str:
        """Return the assistant's full reply for the given prior turns."""
