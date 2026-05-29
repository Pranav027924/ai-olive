"""Unit tests for AnthropicLLMClient (Phase 1.8).

Uses a hand-rolled stub for the Anthropic SDK so tests are offline and
the contract between our adapter and the SDK is explicit. Real-network
verification happens in the E2E test (Phase 1.11) gated on
ANTHROPIC_API_KEY.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from anthropic.types import TextBlock, ToolUseBlock
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


class _StubMessages:
    def __init__(self, reply_text: str = "hi back") -> None:
        self.reply_text = reply_text
        self.last_kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> Any:
        self.last_kwargs = kwargs
        return SimpleNamespace(
            content=[TextBlock(type="text", text=self.reply_text, citations=None)],
        )


class _StubAnthropic:
    def __init__(self, reply_text: str = "hi back") -> None:
        self.messages = _StubMessages(reply_text=reply_text)


@pytest.fixture
def stub() -> _StubAnthropic:
    return _StubAnthropic()


@pytest.fixture
def adapter(stub: _StubAnthropic) -> AnthropicLLMClient:
    return AnthropicLLMClient(api_key="not-used-with-stub", client=stub)  # type: ignore[arg-type]


def _cfg() -> ModelConfig:
    return ModelConfig(provider="anthropic", model="claude-opus-4-7")


async def test_messages_are_mapped_to_anthropic_role_and_content(
    adapter: AnthropicLLMClient, stub: _StubAnthropic
) -> None:
    msgs = [
        _msg(MessageRole.USER, "first", 1),
        _msg(MessageRole.ASSISTANT, "first reply", 2),
        _msg(MessageRole.USER, "second", 3),
    ]

    await adapter.complete(messages=msgs, config=_cfg())

    assert stub.messages.last_kwargs is not None
    assert stub.messages.last_kwargs["messages"] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "first reply"},
        {"role": "user", "content": "second"},
    ]


async def test_system_prompt_is_passed_via_system_kwarg(
    adapter: AnthropicLLMClient, stub: _StubAnthropic
) -> None:
    await adapter.complete(
        messages=[_msg(MessageRole.USER, "hi", 1)],
        config=_cfg(),
        system_prompt="be brief",
    )

    assert stub.messages.last_kwargs is not None
    assert stub.messages.last_kwargs.get("system") == "be brief"


async def test_no_system_kwarg_when_prompt_is_absent(
    adapter: AnthropicLLMClient, stub: _StubAnthropic
) -> None:
    await adapter.complete(messages=[_msg(MessageRole.USER, "hi", 1)], config=_cfg())

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

    await adapter.complete(messages=msgs, config=_cfg())

    assert stub.messages.last_kwargs is not None
    assert stub.messages.last_kwargs["messages"] == [{"role": "user", "content": "hi"}]


async def test_model_and_max_tokens_are_passed_through(
    stub: _StubAnthropic,
) -> None:
    adapter = AnthropicLLMClient(api_key="x", max_tokens=512, client=stub)  # type: ignore[arg-type]
    cfg = ModelConfig(provider="anthropic", model="claude-haiku-4-5")

    await adapter.complete(messages=[_msg(MessageRole.USER, "hi", 1)], config=cfg)

    assert stub.messages.last_kwargs is not None
    assert stub.messages.last_kwargs["model"] == "claude-haiku-4-5"
    assert stub.messages.last_kwargs["max_tokens"] == 512


async def test_first_text_block_is_returned(
    adapter: AnthropicLLMClient, stub: _StubAnthropic
) -> None:
    stub.messages.reply_text = "hello world"

    out = await adapter.complete(messages=[_msg(MessageRole.USER, "hi", 1)], config=_cfg())

    assert out == "hello world"


async def test_returns_empty_string_when_no_text_blocks(
    adapter: AnthropicLLMClient, stub: _StubAnthropic
) -> None:
    async def _no_text(**_: Any) -> Any:
        return SimpleNamespace(content=[ToolUseBlock(type="tool_use", id="x", name="t", input={})])

    stub.messages.create = _no_text  # type: ignore[method-assign]
    out = await adapter.complete(messages=[_msg(MessageRole.USER, "hi", 1)], config=_cfg())

    assert out == ""
