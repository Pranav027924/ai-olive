"""Exhaustive tests for AnthropicAdapter (Phase 3.5)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from anthropic.types import Message, TextBlock, Usage
from olive_sdk.infrastructure.providers.anthropic_adapter import AnthropicAdapter
from olive_sdk.infrastructure.providers.base_adapter import (
    ChatTurn,
    ChunkEvent,
    UsageEvent,
)

# ---------------------------------------------------------------------------
# Anthropic-SDK stub
# ---------------------------------------------------------------------------


def _final_message(*, input_tokens: int = 0, output_tokens: int = 0) -> Message:
    return Message(
        id="msg_x",
        type="message",
        role="assistant",
        model="claude-opus-4-7",
        content=[TextBlock(type="text", text="", citations=None)],
        stop_reason="end_turn",
        stop_sequence=None,
        usage=Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=None,
            cache_read_input_tokens=None,
            server_tool_use=None,
            service_tier=None,
        ),
    )


class _StubStream:
    def __init__(self, *, chunks: list[str], final: Message) -> None:
        self._chunks = list(chunks)
        self._final = final

    @property
    def text_stream(self) -> AsyncIterator[str]:
        async def _iter() -> AsyncIterator[str]:
            for c in self._chunks:
                yield c

        return _iter()

    async def get_final_message(self) -> Message:
        return self._final


class _StubStreamCM:
    def __init__(self, *, chunks: list[str], final: Message) -> None:
        self._chunks = chunks
        self._final = final

    async def __aenter__(self) -> _StubStream:
        return _StubStream(chunks=self._chunks, final=self._final)

    async def __aexit__(self, *_: Any) -> None:
        return None


class _StubMessages:
    def __init__(
        self,
        *,
        chunks: list[str] | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        self.chunks: list[str] = chunks if chunks is not None else ["ok"]
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.last_kwargs: dict[str, Any] | None = None

    def stream(self, **kwargs: Any) -> _StubStreamCM:
        self.last_kwargs = kwargs
        return _StubStreamCM(
            chunks=self.chunks,
            final=_final_message(input_tokens=self.input_tokens, output_tokens=self.output_tokens),
        )


class _StubAnthropic:
    def __init__(
        self,
        *,
        chunks: list[str] | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        self.messages = _StubMessages(
            chunks=chunks, input_tokens=input_tokens, output_tokens=output_tokens
        )


def _adapter(stub: _StubAnthropic, *, max_tokens: int = 4096) -> AnthropicAdapter:
    return AnthropicAdapter(api_key="x", max_tokens=max_tokens, client=stub)  # type: ignore[arg-type]


async def _collect(adapter: AnthropicAdapter, **kwargs: Any) -> list[object]:
    return [e async for e in adapter.stream(**kwargs)]


# ---------------------------------------------------------------------------
# Role + message mapping
# ---------------------------------------------------------------------------


async def test_user_and_assistant_turns_are_mapped_in_order() -> None:
    stub = _StubAnthropic()
    await _collect(
        _adapter(stub),
        model="claude-opus-4-7",
        messages=[
            ChatTurn(role="user", content="first"),
            ChatTurn(role="assistant", content="first reply"),
            ChatTurn(role="user", content="second"),
        ],
    )
    assert stub.messages.last_kwargs is not None
    assert stub.messages.last_kwargs["messages"] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "first reply"},
        {"role": "user", "content": "second"},
    ]


async def test_system_role_turns_are_filtered_from_messages() -> None:
    stub = _StubAnthropic()
    await _collect(
        _adapter(stub),
        model="claude-opus-4-7",
        messages=[
            ChatTurn(role="system", content="internal"),
            ChatTurn(role="user", content="hi"),
        ],
    )
    assert stub.messages.last_kwargs is not None
    assert stub.messages.last_kwargs["messages"] == [{"role": "user", "content": "hi"}]


# ---------------------------------------------------------------------------
# System prompt routing
# ---------------------------------------------------------------------------


async def test_system_prompt_routes_via_system_kwarg() -> None:
    stub = _StubAnthropic()
    await _collect(
        _adapter(stub),
        model="claude-opus-4-7",
        messages=[ChatTurn(role="user", content="hi")],
        system_prompt="be brief",
    )
    assert stub.messages.last_kwargs is not None
    assert stub.messages.last_kwargs.get("system") == "be brief"


async def test_no_system_kwarg_when_prompt_is_none() -> None:
    stub = _StubAnthropic()
    await _collect(
        _adapter(stub),
        model="claude-opus-4-7",
        messages=[ChatTurn(role="user", content="hi")],
    )
    assert stub.messages.last_kwargs is not None
    assert "system" not in stub.messages.last_kwargs


# ---------------------------------------------------------------------------
# Model + max_tokens flow-through
# ---------------------------------------------------------------------------


async def test_model_is_forwarded() -> None:
    stub = _StubAnthropic()
    await _collect(
        _adapter(stub),
        model="claude-haiku-4-5",
        messages=[ChatTurn(role="user", content="hi")],
    )
    assert stub.messages.last_kwargs is not None
    assert stub.messages.last_kwargs["model"] == "claude-haiku-4-5"


async def test_max_tokens_is_forwarded() -> None:
    stub = _StubAnthropic()
    await _collect(
        _adapter(stub, max_tokens=512),
        model="claude-opus-4-7",
        messages=[ChatTurn(role="user", content="hi")],
    )
    assert stub.messages.last_kwargs is not None
    assert stub.messages.last_kwargs["max_tokens"] == 512


# ---------------------------------------------------------------------------
# Event ordering and shape
# ---------------------------------------------------------------------------


async def test_chunks_then_exactly_one_usage_event_in_that_order() -> None:
    stub = _StubAnthropic(chunks=["a", "b", "c"], input_tokens=10, output_tokens=20)
    events = await _collect(
        _adapter(stub),
        model="claude-opus-4-7",
        messages=[ChatTurn(role="user", content="hi")],
    )

    assert [type(e).__name__ for e in events] == [
        "ChunkEvent",
        "ChunkEvent",
        "ChunkEvent",
        "UsageEvent",
    ]
    assert [e.text for e in events[:-1] if isinstance(e, ChunkEvent)] == ["a", "b", "c"]
    last = events[-1]
    assert isinstance(last, UsageEvent)
    assert last.prompt_tokens == 10
    assert last.completion_tokens == 20


async def test_empty_response_still_yields_usage_event() -> None:
    stub = _StubAnthropic(chunks=[], input_tokens=5, output_tokens=0)
    events = await _collect(
        _adapter(stub),
        model="claude-opus-4-7",
        messages=[ChatTurn(role="user", content="hi")],
    )

    assert len(events) == 1
    last = events[0]
    assert isinstance(last, UsageEvent)
    assert last.prompt_tokens == 5
    assert last.completion_tokens == 0


@pytest.mark.parametrize(
    ("input_tokens", "output_tokens"),
    [(0, 0), (1, 0), (0, 1), (1, 1), (123, 456)],
)
async def test_usage_event_carries_provider_token_counts(
    input_tokens: int, output_tokens: int
) -> None:
    stub = _StubAnthropic(chunks=["x"], input_tokens=input_tokens, output_tokens=output_tokens)
    events = await _collect(
        _adapter(stub),
        model="claude-opus-4-7",
        messages=[ChatTurn(role="user", content="hi")],
    )

    usage = events[-1]
    assert isinstance(usage, UsageEvent)
    assert usage.prompt_tokens == input_tokens
    assert usage.completion_tokens == output_tokens
