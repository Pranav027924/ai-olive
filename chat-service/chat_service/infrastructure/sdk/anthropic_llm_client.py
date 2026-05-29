"""AnthropicLLMClient — direct Anthropic adapter for the LLMClient port.

Phase 2.4 wires the adapter to Anthropic's real streaming API
(``messages.stream(...).text_stream``). The Phase 2.2 placeholder that
yielded the full reply as one chunk is gone.

Notes:
- Anthropic only accepts ``user`` and ``assistant`` roles. ``system``
  is passed via the ``system`` kwarg; any ``system`` messages in the
  context are dropped here. ``tool`` is unused in Phase 1 / 2.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam

from chat_service.application.ports.llm_client import LLMClient
from chat_service.domain.entities.message import Message
from chat_service.domain.value_objects.message_role import MessageRole
from chat_service.domain.value_objects.model_config import ModelConfig

DEFAULT_MAX_TOKENS = 4096


class AnthropicLLMClient(LLMClient):
    def __init__(
        self,
        *,
        api_key: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        client: AsyncAnthropic | None = None,
    ) -> None:
        self._client = client or AsyncAnthropic(api_key=api_key)
        self._max_tokens = max_tokens

    async def stream(
        self,
        *,
        messages: list[Message],
        config: ModelConfig,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        anthropic_messages: list[MessageParam] = [
            {
                "role": "user" if m.role is MessageRole.USER else "assistant",
                "content": m.content,
            }
            for m in messages
            if m.role in (MessageRole.USER, MessageRole.ASSISTANT)
        ]

        if system_prompt:
            stream_cm = self._client.messages.stream(
                model=config.model,
                max_tokens=self._max_tokens,
                messages=anthropic_messages,
                system=system_prompt,
            )
        else:
            stream_cm = self._client.messages.stream(
                model=config.model,
                max_tokens=self._max_tokens,
                messages=anthropic_messages,
            )

        async with stream_cm as stream:
            async for delta in stream.text_stream:
                yield delta
