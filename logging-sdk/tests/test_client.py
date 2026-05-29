"""Tests for the public LLMClient (Phase 3.9)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from contracts.log_event import LogEvent
from olive_sdk.client import SDK_VERSION, LLMClient
from olive_sdk.infrastructure.providers.base_adapter import (
    ChatTurn,
    ChunkEvent,
    ProviderAdapter,
    ProviderEvent,
    UsageEvent,
)


class _CapturingEmitter:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    async def emit(self, event: LogEvent) -> None:
        self.events.append(event)


class _FakeAdapter(ProviderAdapter):
    """Pre-canned event sequence, records inputs."""

    def __init__(
        self,
        *,
        chunks: list[str] | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        self.chunks: list[str] = chunks if chunks is not None else ["hi"]
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.received_model: str | None = None
        self.received_messages: list[ChatTurn] | None = None
        self.received_system_prompt: str | None = None

    async def stream(
        self,
        *,
        model: str,
        messages: list[ChatTurn],
        system_prompt: str | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        self.received_model = model
        self.received_messages = list(messages)
        self.received_system_prompt = system_prompt
        for c in self.chunks:
            yield ChunkEvent(text=c)
        yield UsageEvent(prompt_tokens=self.prompt_tokens, completion_tokens=self.completion_tokens)


def _client(adapter: ProviderAdapter, emitter: _CapturingEmitter) -> LLMClient:
    return LLMClient(
        provider="anthropic",
        model="claude-opus-4-7",
        emitter=emitter,
        adapter=adapter,
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_unsupported_provider_raises_when_no_adapter_injected() -> None:
    with pytest.raises(ValueError, match="unsupported provider"):
        LLMClient(
            provider="cohere",
            model="command-r",
            emitter=_CapturingEmitter(),
        )


# ---------------------------------------------------------------------------
# Streaming + LogEvent emission
# ---------------------------------------------------------------------------


async def test_complete_yields_chunks_then_emits_log_event() -> None:
    adapter = _FakeAdapter(chunks=["he", "llo"], prompt_tokens=12, completion_tokens=34)
    emitter = _CapturingEmitter()
    client = _client(adapter, emitter)

    sid = uuid4()
    mid = uuid4()
    tokens = [
        t
        async for t in client.complete(
            session_id=sid,
            message_id=mid,
            messages=[ChatTurn(role="user", content="hi there")],
        )
    ]

    assert tokens == ["he", "llo"]
    assert len(emitter.events) == 1
    ev = emitter.events[0]
    assert ev.session_id == sid
    assert ev.message_id == mid
    assert ev.provider == "anthropic"
    assert ev.model == "claude-opus-4-7"
    assert ev.status == "success"
    assert ev.prompt_tokens == 12
    assert ev.completion_tokens == 34
    assert ev.sdk_version == SDK_VERSION
    assert ev.output_preview == "hello"
    assert ev.input_preview == "[user] hi there"  # default summary


async def test_explicit_input_preview_overrides_default() -> None:
    adapter = _FakeAdapter()
    emitter = _CapturingEmitter()
    client = _client(adapter, emitter)

    async for _ in client.complete(
        session_id=uuid4(),
        messages=[ChatTurn(role="user", content="hi")],
        input_preview="custom preview",
    ):
        pass

    assert emitter.events[0].input_preview == "custom preview"


async def test_event_id_can_be_injected() -> None:
    fixed = uuid4()
    adapter = _FakeAdapter()
    emitter = _CapturingEmitter()
    client = _client(adapter, emitter)

    async for _ in client.complete(
        session_id=uuid4(),
        messages=[ChatTurn(role="user", content="hi")],
        event_id=fixed,
    ):
        pass

    assert emitter.events[0].event_id == fixed


async def test_adapter_receives_model_and_system_prompt() -> None:
    adapter = _FakeAdapter()
    emitter = _CapturingEmitter()
    client = _client(adapter, emitter)

    async for _ in client.complete(
        session_id=uuid4(),
        messages=[ChatTurn(role="user", content="hi")],
        system_prompt="be brief",
    ):
        pass

    assert adapter.received_model == "claude-opus-4-7"
    assert adapter.received_system_prompt == "be brief"
    assert adapter.received_messages == [ChatTurn(role="user", content="hi")]


async def test_default_event_id_is_unique_per_call() -> None:
    adapter = _FakeAdapter()
    emitter = _CapturingEmitter()
    client = _client(adapter, emitter)
    sid = uuid4()

    async for _ in client.complete(session_id=sid, messages=[ChatTurn(role="user", content="a")]):
        pass
    async for _ in client.complete(session_id=sid, messages=[ChatTurn(role="user", content="b")]):
        pass

    assert emitter.events[0].event_id != emitter.events[1].event_id
