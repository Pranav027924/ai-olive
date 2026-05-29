"""Smoke test for AnthropicAdapter (Phase 3.4).

Detailed coverage (system prompt routing, role mapping, multiple
chunks, usage shape) lands in Phase 3.5.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from anthropic.types import Message, TextBlock, Usage
from olive_sdk.infrastructure.providers.anthropic_adapter import AnthropicAdapter
from olive_sdk.infrastructure.providers.base_adapter import (
    ChatTurn,
    ChunkEvent,
    UsageEvent,
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
    def __init__(self) -> None:
        self.last_kwargs: dict[str, Any] | None = None

    def stream(self, **kwargs: Any) -> _StubStreamCM:
        self.last_kwargs = kwargs
        return _StubStreamCM(
            chunks=["hi", " ", "there"],
            final=_message(input_tokens=42, output_tokens=7),
        )


class _StubAnthropic:
    def __init__(self) -> None:
        self.messages = _StubMessages()


def _message(*, input_tokens: int, output_tokens: int) -> Message:
    """Build a minimal anthropic Message with the fields the adapter reads."""
    return Message(
        id="msg_x",
        type="message",
        role="assistant",
        model="claude-opus-4-7",
        content=[TextBlock(type="text", text="hi there", citations=None)],
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


async def test_yields_chunks_then_usage() -> None:
    adapter = AnthropicAdapter(api_key="x", client=_StubAnthropic())  # type: ignore[arg-type]
    events = [
        e
        async for e in adapter.stream(
            model="claude-opus-4-7",
            messages=[ChatTurn(role="user", content="hi")],
        )
    ]

    chunks = [e for e in events if isinstance(e, ChunkEvent)]
    usages = [e for e in events if isinstance(e, UsageEvent)]

    assert [c.text for c in chunks] == ["hi", " ", "there"]
    assert len(usages) == 1
    assert usages[0].prompt_tokens == 42
    assert usages[0].completion_tokens == 7
    assert events[-1] is usages[0]
