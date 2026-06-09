"""GeminiAdapter — ProviderAdapter for Google Gemini via google-genai (PRD §7.1).

Uses the modern :class:`google.genai.Client` async streaming API. The
SDK emits ``usage_metadata`` on the final chunk; we capture token
counts as they arrive and emit a single :class:`UsageEvent` at the
end so the consumer sees the same event shape as the Anthropic /
OpenAI adapters.

For tests we accept a pre-built ``client`` (anything with the same
``client.aio.models.generate_content_stream(...)`` async-iterable
return) so unit tests don't need a real API key.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from google import genai
from google.genai import types as genai_types

from olive_sdk.infrastructure.providers.base_adapter import (
    ChatTurn,
    ChunkEvent,
    ProviderAdapter,
    ProviderEvent,
    UsageEvent,
)


class _GenaiClientLike(Protocol):
    @property
    def aio(self) -> Any: ...


class GeminiAdapter(ProviderAdapter):
    def __init__(
        self,
        *,
        api_key: str = "",
        client: _GenaiClientLike | None = None,
    ) -> None:
        self._client = client or genai.Client(api_key=api_key)

    async def stream(
        self,
        *,
        model: str,
        messages: list[ChatTurn],
        system_prompt: str | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        contents: list[dict[str, Any]] = [
            {
                "role": "model" if t.role == "assistant" else "user",
                "parts": [{"text": t.content}],
            }
            for t in messages
            if t.role in ("user", "assistant")
        ]

        config = None
        if system_prompt:
            config = genai_types.GenerateContentConfig(system_instruction=system_prompt)

        stream = await self._client.aio.models.generate_content_stream(
            model=model,
            contents=contents,  # type: ignore[arg-type]
            config=config,
        )

        prompt_tokens = 0
        completion_tokens = 0
        async for chunk in stream:
            text = getattr(chunk, "text", "") or ""
            if text:
                yield ChunkEvent(text=text)
            usage = getattr(chunk, "usage_metadata", None)
            if usage is not None:
                prompt_tokens = getattr(usage, "prompt_token_count", prompt_tokens) or 0
                completion_tokens = getattr(usage, "candidates_token_count", completion_tokens) or 0

        yield UsageEvent(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
