"""LLMClient — outbound port for calling an LLM provider.

Phase 2 widens the port to an async generator. The blocking variant
from Phase 1 is gone; callers that want a single string can collect
the stream with ``"".join([chunk async for chunk in llm.stream(...)])``.

Adapters arrive in:
  - Phase 2.4: AnthropicLLMClient.stream uses Anthropic's
    messages.stream() text_stream.
  - Phase 3.10: a logging-SDK wrapper around the same port.

The Protocol must stay narrow so future adapters (OpenAI, Gemini,
DeepSeek in Phase 7.1) only need to satisfy one method.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from chat_service.domain.entities.message import Message
from chat_service.domain.value_objects.model_config import ModelConfig


class LLMClient(Protocol):
    """Async port that yields text deltas as they arrive from the LLM."""

    def stream(
        self,
        *,
        messages: list[Message],
        config: ModelConfig,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield text chunks of the assistant's reply in order."""
