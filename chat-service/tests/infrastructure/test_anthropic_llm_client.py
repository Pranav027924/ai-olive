"""Unit tests for AnthropicLLMClient (Phase 2.4).

The stub mirrors the shape of ``AsyncAnthropic.messages.stream(...)``:
it returns an async context manager whose body exposes
``text_stream`` as an AsyncIterable[str].

Real-network verification happens in the Phase 2.8 e2e tests gated on
ANTHROPIC_API_KEY.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from chat_service.domain.entities.message import Message
from chat_service.domain.value_objects.message_role import MessageRole
from chat_service.domain.value_objects.message_status import MessageStatus
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.infrastructure.sdk.anthropic_llm_client import AnthropicLLMClient


def _msg(role: MessageRole, content: str, seq: int) -> Message:
    return Message(
        id=uuid4(),
        role=role,
        content=content,
        seq=seq,
        status=MessageStatus.COMPLETE,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class _StubStream:
    """Mimics the object yielded by `async with messages.stream(...) as s`."""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = list(chunks)

    @property
    def text_stream(self) -> AsyncIterator[str]:
        async def _iter() -> AsyncIterator[str]:
            for c in self._chunks:
                yield c

        return _iter()


class _StubStreamCM:
    """Async context manager returned by `messages.stream(...)`."""

    def __init__(self, *, chunks: list[str], capture: dict[str, Any]) -> None:
        self._chunks = list(chunks)
        self._capture = capture

    async def __aenter__(self) -> _StubStream:
        return _StubStream(self._chunks)

    async def __aexit__(self, *_: Any) -> None:
        return None


class _StubMessages:
    def __init__(self, chunks: list[str] | None = None) -> None:
        self.chunks: list[str] = chunks if chunks is not None else ["hi back"]
        self.last_kwargs: dict[str, Any] | None = None

    def stream(self, **kwargs: Any) -> _StubStreamCM:
        self.last_kwargs = kwargs
        return _StubStreamCM(chunks=self.chunks, capture=kwargs)


class _StubAnthropic:
    def __init__(self, chunks: list[str] | None = None) -> None:
        self.messages = _StubMessages(chunks=chunks)


@pytest.fixture
def stub() -> _StubAnthropic:
    return _StubAnthropic()


@pytest.fixture
def adapter(stub: _StubAnthropic) -> AnthropicLLMClient:
    return AnthropicLLMClient(api_key="not-used-with-stub", client=stub)  # type: ignore[arg-type]


def _cfg() -> ModelConfig:
    return ModelConfig(provider="anthropic", model="claude-opus-4-7")


async def _collect(adapter: AnthropicLLMClient, **kwargs: Any) -> list[str]:
    return [c async for c in adapter.stream(**kwargs)]


# ---------------------------------------------------------------------------
# Message + kwargs mapping
# ---------------------------------------------------------------------------


async def test_messages_are_mapped_to_anthropic_role_and_content(
    adapter: AnthropicLLMClient, stub: _StubAnthropic
) -> None:
    msgs = [
        _msg(MessageRole.USER, "first", 1),
        _msg(MessageRole.ASSISTANT, "first reply", 2),
        _msg(MessageRole.USER, "second", 3),
    ]

    await _collect(adapter, messages=msgs, config=_cfg())

    assert stub.messages.last_kwargs is not None
    assert stub.messages.last_kwargs["messages"] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "first reply"},
        {"role": "user", "content": "second"},
    ]


async def test_system_prompt_is_passed_via_system_kwarg(
    adapter: AnthropicLLMClient, stub: _StubAnthropic
) -> None:
    await _collect(
        adapter,
        messages=[_msg(MessageRole.USER, "hi", 1)],
        config=_cfg(),
        system_prompt="be brief",
    )

    assert stub.messages.last_kwargs is not None
    assert stub.messages.last_kwargs.get("system") == "be brief"


async def test_no_system_kwarg_when_prompt_is_absent(
    adapter: AnthropicLLMClient, stub: _StubAnthropic
) -> None:
    await _collect(adapter, messages=[_msg(MessageRole.USER, "hi", 1)], config=_cfg())

    assert stub.messages.last_kwargs is not None
    assert "system" not in stub.messages.last_kwargs


async def test_system_and_tool_messages_are_filtered_from_message_list(
    adapter: AnthropicLLMClient, stub: _StubAnthropic
) -> None:
    msgs = [
        _msg(MessageRole.SYSTEM, "internal context", 1),
        _msg(MessageRole.USER, "hi", 2),
        _msg(MessageRole.TOOL, "tool output", 3),
    ]

    await _collect(adapter, messages=msgs, config=_cfg())

    assert stub.messages.last_kwargs is not None
    assert stub.messages.last_kwargs["messages"] == [{"role": "user", "content": "hi"}]


async def test_model_and_max_tokens_are_passed_through(
    stub: _StubAnthropic,
) -> None:
    adapter = AnthropicLLMClient(api_key="x", max_tokens=512, client=stub)  # type: ignore[arg-type]
    cfg = ModelConfig(provider="anthropic", model="claude-haiku-4-5")

    await _collect(adapter, messages=[_msg(MessageRole.USER, "hi", 1)], config=cfg)

    assert stub.messages.last_kwargs is not None
    assert stub.messages.last_kwargs["model"] == "claude-haiku-4-5"
    assert stub.messages.last_kwargs["max_tokens"] == 512


# ---------------------------------------------------------------------------
# Streaming behaviour
# ---------------------------------------------------------------------------


async def test_stream_yields_text_chunks_in_order(stub: _StubAnthropic) -> None:
    stub.messages.chunks = ["hel", "lo ", "world"]
    adapter = AnthropicLLMClient(api_key="x", client=stub)  # type: ignore[arg-type]

    chunks = await _collect(adapter, messages=[_msg(MessageRole.USER, "hi", 1)], config=_cfg())

    assert chunks == ["hel", "lo ", "world"]


async def test_stream_yields_nothing_for_empty_response(stub: _StubAnthropic) -> None:
    stub.messages.chunks = []
    adapter = AnthropicLLMClient(api_key="x", client=stub)  # type: ignore[arg-type]

    chunks = await _collect(adapter, messages=[_msg(MessageRole.USER, "hi", 1)], config=_cfg())

    assert chunks == []
