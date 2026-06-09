"""OpenAIAdapter — ProviderAdapter for the OpenAI Chat Completions API (PRD §7.1).

Wraps :class:`openai.AsyncOpenAI` chat-completion streaming. We ask
for usage in the final chunk via ``stream_options={"include_usage": True}``
so we get a real :class:`UsageEvent` instead of guessing from
``tiktoken``. DeepSeek is OpenAI-wire-compatible and reuses this
adapter via a custom ``base_url``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

from openai import AsyncOpenAI

from olive_sdk.infrastructure.providers.base_adapter import (
    ChatTurn,
    ChunkEvent,
    ProviderAdapter,
    ProviderEvent,
    UsageEvent,
)


class OpenAIAdapter(ProviderAdapter):
    def __init__(
        self,
        *,
        api_key: str = "",
        base_url: str | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        if client is not None:
            self._client = client
        else:
            kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url is not None:
                kwargs["base_url"] = base_url
            self._client = AsyncOpenAI(**kwargs)

    async def stream(
        self,
        *,
        model: str,
        messages: list[ChatTurn],
        system_prompt: str | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        wire_messages: list[dict[str, str]] = []
        if system_prompt:
            wire_messages.append({"role": "system", "content": system_prompt})
        wire_messages.extend({"role": t.role, "content": t.content} for t in messages)

        stream = await self._client.chat.completions.create(
            model=model,
            messages=cast(Any, wire_messages),
            stream=True,
            stream_options={"include_usage": True},
        )

        prompt_tokens = 0
        completion_tokens = 0
        async for event in stream:
            if event.choices:
                delta = event.choices[0].delta
                if delta and delta.content:
                    yield ChunkEvent(text=delta.content)
            if event.usage is not None:
                prompt_tokens = event.usage.prompt_tokens
                completion_tokens = event.usage.completion_tokens

        yield UsageEvent(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
