"""Tests for OpenAIAdapter (Phase 7.2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from olive_sdk.infrastructure.providers.base_adapter import (
    ChatTurn,
    ChunkEvent,
    UsageEvent,
)
from olive_sdk.infrastructure.providers.openai_adapter import OpenAIAdapter


@dataclass
class _Delta:
    content: str | None


@dataclass
class _Choice:
    delta: _Delta


@dataclass
class _Usage:
    prompt_tokens: int
    completion_tokens: int


@dataclass
class _StreamEvent:
    choices: list[_Choice]
    usage: _Usage | None = None


class _StubStream:
    def __init__(self, events: list[_StreamEvent]) -> None:
        self._events = list(events)

    def __aiter__(self) -> AsyncIterator[_StreamEvent]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[_StreamEvent]:
        for ev in self._events:
            yield ev


class _StubCompletions:
    def __init__(self, events: list[_StreamEvent]) -> None:
        self._events = events
        self.received: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> _StubStream:
        self.received = kwargs
        return _StubStream(self._events)


class _StubChat:
    def __init__(self, events: list[_StreamEvent]) -> None:
        self.completions = _StubCompletions(events)


class _StubClient:
    def __init__(self, events: list[_StreamEvent]) -> None:
        self.chat = _StubChat(events)


def _chunk(text: str) -> _StreamEvent:
    return _StreamEvent(choices=[_Choice(delta=_Delta(content=text))])


def _usage(prompt: int, completion: int) -> _StreamEvent:
    return _StreamEvent(choices=[], usage=_Usage(prompt, completion))


async def test_chunks_and_usage_are_emitted_in_order() -> None:
    client = _StubClient([_chunk("hello"), _chunk(" world"), _usage(7, 3)])
    adapter = OpenAIAdapter(client=client)  # type: ignore[arg-type]

    events = [
        ev
        async for ev in adapter.stream(
            model="gpt-4o-mini",
            messages=[ChatTurn(role="user", content="hi")],
        )
    ]

    assert events == [ChunkEvent("hello"), ChunkEvent(" world"), UsageEvent(7, 3)]


async def test_system_prompt_is_prepended_to_messages() -> None:
    client = _StubClient([_chunk("ok"), _usage(1, 1)])
    adapter = OpenAIAdapter(client=client)  # type: ignore[arg-type]

    async for _ in adapter.stream(
        model="gpt-4o",
        messages=[ChatTurn(role="user", content="hi")],
        system_prompt="be brief",
    ):
        pass

    received = client.chat.completions.received
    assert received is not None
    assert received["messages"][0] == {"role": "system", "content": "be brief"}
    assert received["messages"][1] == {"role": "user", "content": "hi"}
    assert received["stream"] is True
    assert received["stream_options"] == {"include_usage": True}


async def test_missing_usage_yields_zero_token_event() -> None:
    """Compatible providers (DeepSeek edge case) sometimes omit usage."""
    client = _StubClient([_chunk("ok")])
    adapter = OpenAIAdapter(client=client)  # type: ignore[arg-type]

    events = [
        ev
        async for ev in adapter.stream(
            model="gpt-4o-mini",
            messages=[ChatTurn(role="user", content="hi")],
        )
    ]

    assert events[-1] == UsageEvent(0, 0)


async def test_empty_delta_chunks_are_skipped() -> None:
    """The first event from OpenAI is usually an empty delta — skip it."""
    empty = _StreamEvent(choices=[_Choice(delta=_Delta(content=None))])
    client = _StubClient([empty, _chunk("hi"), _usage(1, 1)])
    adapter = OpenAIAdapter(client=client)  # type: ignore[arg-type]

    events = [
        ev
        async for ev in adapter.stream(
            model="gpt-4o-mini",
            messages=[ChatTurn(role="user", content="hi")],
        )
    ]

    assert events == [ChunkEvent("hi"), UsageEvent(1, 1)]
