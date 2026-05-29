"""LLMClient — public SDK API (PRD §6.2, Phase 3.9).

Wraps a ProviderAdapter and a Tracker so callers can stream tokens
without owning the LogEvent lifecycle::

    client = LLMClient(
        provider="anthropic",
        model="claude-opus-4-7",
        emitter=FileEmitter(),
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )

    async for token in client.complete(
        session_id=session_id,
        message_id=message_id,
        messages=[ChatTurn(role="user", content="hi")],
        system_prompt="be brief",
    ):
        print(token, end="")
    # On exit a LogEvent has been shipped through the emitter with
    # provider/model/tokens/latency/ttft/preview etc. populated.

Injection points:
- ``adapter=…`` swap in a pre-built ProviderAdapter (e.g. for tests).
- ``emitter=…`` swap in any EmitterPort (FileEmitter, HTTPEmitter,
  CompositeEmitter).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Final
from uuid import UUID

from olive_sdk.application.emitter_port import EmitterPort
from olive_sdk.application.tracker import Tracker
from olive_sdk.infrastructure.providers.anthropic_adapter import AnthropicAdapter
from olive_sdk.infrastructure.providers.base_adapter import (
    ChatTurn,
    ChunkEvent,
    ProviderAdapter,
    UsageEvent,
)

SDK_VERSION: Final = "0.1.0"


def _build_adapter(provider: str, *, api_key: str) -> ProviderAdapter:
    """Default ProviderAdapter for a provider name.

    Only ``anthropic`` is supported in Phase 3; OpenAI / Gemini /
    DeepSeek adapters land in Phase 7.1.
    """
    if provider == "anthropic":
        return AnthropicAdapter(api_key=api_key)
    raise ValueError(f"unsupported provider: {provider!r}")


def _default_input_preview(messages: list[ChatTurn]) -> str:
    return "\n".join(f"[{m.role}] {m.content}" for m in messages)


class LLMClient:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        emitter: EmitterPort,
        api_key: str = "",
        adapter: ProviderAdapter | None = None,
        sdk_version: str = SDK_VERSION,
    ) -> None:
        self._provider = provider
        self._model = model
        self._emitter = emitter
        self._sdk_version = sdk_version
        self._adapter: ProviderAdapter = adapter or _build_adapter(provider, api_key=api_key)

    async def complete(
        self,
        *,
        session_id: UUID,
        messages: list[ChatTurn],
        message_id: UUID | None = None,
        system_prompt: str | None = None,
        input_preview: str | None = None,
        event_id: UUID | None = None,
    ) -> AsyncIterator[str]:
        """Yield text deltas; build + emit a LogEvent on exit.

        Pass ``input_preview`` to override the default
        ``"[role] content"`` summary built from ``messages``.
        """
        preview = input_preview if input_preview is not None else _default_input_preview(messages)

        tracker = Tracker(
            emitter=self._emitter,
            session_id=session_id,
            message_id=message_id,
            event_id=event_id,
            provider=self._provider,
            model=self._model,
            sdk_version=self._sdk_version,
            input_preview=preview,
        )

        async with tracker:
            async for event in self._adapter.stream(
                model=self._model,
                messages=messages,
                system_prompt=system_prompt,
            ):
                if isinstance(event, ChunkEvent):
                    tracker.record_chunk(event.text)
                    yield event.text
                elif isinstance(event, UsageEvent):
                    tracker.record_usage(event.prompt_tokens, event.completion_tokens)
