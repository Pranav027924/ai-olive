"""Tests for GeminiAdapter (Phase 7.2).

Uses a fake client that mimics the async streaming interface of the
``google.genai`` SDK so we exercise the adapter without hitting the
real API.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from olive_sdk.infrastructure.providers.base_adapter import (
    ChatTurn,
    ChunkEvent,
    UsageEvent,
)
from olive_sdk.infrastructure.providers.gemini_adapter import GeminiAdapter


@dataclass
class _Usage:
    prompt_token_count: int
    candidates_token_count: int


@dataclass
class _Chunk:
    text: str
    usage_metadata: _Usage | None = None


class _StubStream:
    def __init__(self, chunks: list[_Chunk]) -> None:
        self._chunks = list(chunks)

    def __aiter__(self) -> AsyncIterator[_Chunk]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[_Chunk]:
        for c in self._chunks:
            yield c


class _StubModels:
    def __init__(self, chunks: list[_Chunk]) -> None:
        self._chunks = chunks
        self.received: dict[str, Any] | None = None

    async def generate_content_stream(self, **kwargs: Any) -> _StubStream:
        self.received = kwargs
        return _StubStream(self._chunks)


class _StubAio:
    def __init__(self, chunks: list[_Chunk]) -> None:
        self.models = _StubModels(chunks)


class _StubClient:
    def __init__(self, chunks: list[_Chunk]) -> None:
        self.aio = _StubAio(chunks)


async def test_chunks_and_final_usage_are_emitted() -> None:
    client = _StubClient(
        [
            _Chunk(text="hi "),
            _Chunk(text="there", usage_metadata=_Usage(4, 2)),
        ]
    )
    adapter = GeminiAdapter(client=client)

    events = [
        ev
        async for ev in adapter.stream(
            model="gemini-2.0-flash",
            messages=[ChatTurn(role="user", content="hi")],
        )
    ]

    assert events == [ChunkEvent("hi "), ChunkEvent("there"), UsageEvent(4, 2)]


async def test_assistant_role_maps_to_gemini_model_role() -> None:
    client = _StubClient([_Chunk(text="ok", usage_metadata=_Usage(1, 1))])
    adapter = GeminiAdapter(client=client)

    async for _ in adapter.stream(
        model="gemini-2.0-flash",
        messages=[
            ChatTurn(role="user", content="hi"),
            ChatTurn(role="assistant", content="prior"),
        ],
    ):
        pass

    assert client.aio.models.received is not None
    assert client.aio.models.received["contents"] == [
        {"role": "user", "parts": [{"text": "hi"}]},
        {"role": "model", "parts": [{"text": "prior"}]},
    ]


async def test_system_prompt_is_forwarded_via_config() -> None:
    client = _StubClient([_Chunk(text="ok", usage_metadata=_Usage(1, 1))])
    adapter = GeminiAdapter(client=client)

    async for _ in adapter.stream(
        model="gemini-2.0-flash",
        messages=[ChatTurn(role="user", content="hi")],
        system_prompt="be brief",
    ):
        pass

    assert client.aio.models.received is not None
    config = client.aio.models.received["config"]
    assert config is not None
    assert config.system_instruction == "be brief"


async def test_missing_usage_yields_zero_token_event() -> None:
    client = _StubClient([_Chunk(text="ok")])  # no usage_metadata anywhere
    adapter = GeminiAdapter(client=client)

    events = [
        ev
        async for ev in adapter.stream(
            model="gemini-2.0-flash",
            messages=[ChatTurn(role="user", content="hi")],
        )
    ]

    assert events[-1] == UsageEvent(0, 0)
