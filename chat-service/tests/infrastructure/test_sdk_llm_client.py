"""Tests for SdkLlmClient per-provider routing (Phase 7.3).

These don't talk to any real provider — we patch the SDK adapter
constructor to inspect what api_key each provider gets handed when
the chat-service routes a session through SdkLlmClient.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar
from uuid import uuid4

import pytest
from chat_service.domain.entities.message import Message
from chat_service.domain.value_objects.message_role import MessageRole
from chat_service.domain.value_objects.message_status import MessageStatus
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.infrastructure.sdk.sdk_llm_client import SdkLlmClient
from olive_sdk.application.emitter_port import EmitterPort
from olive_sdk.infrastructure.providers.base_adapter import (
    ChatTurn,
    ChunkEvent,
    ProviderEvent,
    UsageEvent,
)


class _NullEmitter(EmitterPort):
    async def emit(self, event: Any) -> None:
        return None


class _StubAdapter:
    instances: ClassVar[list[_StubAdapter]] = []

    def __init__(self, *, api_key: str, **_: Any) -> None:
        self.api_key = api_key
        _StubAdapter.instances.append(self)

    async def stream(
        self, *, model: str, messages: list[ChatTurn], system_prompt: str | None = None
    ) -> AsyncIterator[ProviderEvent]:
        yield ChunkEvent(text="ok")
        yield UsageEvent(prompt_tokens=1, completion_tokens=1)


@pytest.fixture(autouse=True)
def patch_adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    _StubAdapter.instances.clear()
    import olive_sdk.client as sdk_client

    monkeypatch.setattr(sdk_client, "AnthropicAdapter", _StubAdapter)
    monkeypatch.setattr(sdk_client, "OpenAIAdapter", _StubAdapter)
    monkeypatch.setattr(sdk_client, "GeminiAdapter", _StubAdapter)
    monkeypatch.setattr(sdk_client, "DeepSeekAdapter", _StubAdapter)


def _user_message(content: str) -> Message:
    from datetime import UTC, datetime

    return Message(
        id=uuid4(),
        role=MessageRole.USER,
        content=content,
        seq=1,
        status=MessageStatus.COMPLETE,
        created_at=datetime(2026, 6, 4, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("provider", "expected_key"),
    [
        ("anthropic", "ant-key"),
        ("openai", "oai-key"),
        ("gemini", "gem-key"),
        ("deepseek", "ds-key"),
    ],
)
async def test_per_provider_api_key_is_handed_to_the_adapter(
    provider: str, expected_key: str
) -> None:
    client = SdkLlmClient(
        emitter=_NullEmitter(),
        api_keys={
            "anthropic": "ant-key",
            "openai": "oai-key",
            "gemini": "gem-key",
            "deepseek": "ds-key",
        },
    )

    async for _ in client.stream(
        session_id=uuid4(),
        message_id=uuid4(),
        messages=[_user_message("hi")],
        config=ModelConfig(provider=provider, model="m"),
    ):
        pass

    assert _StubAdapter.instances[-1].api_key == expected_key


async def test_unknown_provider_gets_empty_key_without_raising() -> None:
    """Defensive: an unconfigured provider falls back to "" rather than
    crashing — the adapter itself will surface the auth error when it
    actually talks to the API."""
    client = SdkLlmClient(emitter=_NullEmitter(), api_keys={"anthropic": "ak"})

    # Patch out _build_adapter to accept "openai" without raising even
    # though api_keys["openai"] is absent.
    async for _ in client.stream(
        session_id=uuid4(),
        message_id=uuid4(),
        messages=[_user_message("hi")],
        config=ModelConfig(provider="openai", model="gpt-4o-mini"),
    ):
        pass

    assert _StubAdapter.instances[-1].api_key == ""
