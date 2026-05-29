"""AnthropicAdapter — concrete ProviderAdapter for Anthropic (Phase 3.4).

Wraps ``AsyncAnthropic.messages.stream(...).text_stream``, yielding
ChunkEvents during the stream and a UsageEvent built from
``stream.get_final_message().usage`` after the stream closes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam

from olive_sdk.infrastructure.providers.base_adapter import (
    ChatTurn,
    ChunkEvent,
    ProviderAdapter,
    ProviderEvent,
    UsageEvent,
)

DEFAULT_MAX_TOKENS = 4096


class AnthropicAdapter(ProviderAdapter):
    def __init__(
        self,
        *,
        api_key: str = "",
        max_tokens: int = DEFAULT_MAX_TOKENS,
        client: AsyncAnthropic | None = None,
    ) -> None:
        self._client = client or AsyncAnthropic(api_key=api_key)
        self._max_tokens = max_tokens

    async def stream(
        self,
        *,
        model: str,
        messages: list[ChatTurn],
        system_prompt: str | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        anthropic_messages: list[MessageParam] = [
            {
                "role": "user" if t.role == "user" else "assistant",
                "content": t.content,
            }
            for t in messages
            if t.role in ("user", "assistant")
        ]

        if system_prompt:
            stream_cm = self._client.messages.stream(
                model=model,
                max_tokens=self._max_tokens,
                messages=anthropic_messages,
                system=system_prompt,
            )
        else:
            stream_cm = self._client.messages.stream(
                model=model,
                max_tokens=self._max_tokens,
                messages=anthropic_messages,
            )

        async with stream_cm as stream:
            async for delta in stream.text_stream:
                yield ChunkEvent(text=delta)
            final = await stream.get_final_message()
            yield UsageEvent(
                prompt_tokens=final.usage.input_tokens,
                completion_tokens=final.usage.output_tokens,
            )
