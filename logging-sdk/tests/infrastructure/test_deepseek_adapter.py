"""Tests for DeepSeekAdapter (Phase 7.2)."""

from __future__ import annotations

from olive_sdk.infrastructure.providers.deepseek_adapter import (
    DEEPSEEK_BASE_URL,
    DeepSeekAdapter,
)
from olive_sdk.infrastructure.providers.openai_adapter import OpenAIAdapter


def test_deepseek_adapter_is_an_openai_subclass() -> None:
    """DeepSeek piggybacks on the OpenAI wire format — keep the
    inheritance assertion so a future refactor can't accidentally
    sever the relationship."""
    assert issubclass(DeepSeekAdapter, OpenAIAdapter)


def test_deepseek_base_url_constant_is_pinned_to_official_host() -> None:
    """If DeepSeek ever changes hostnames we want a single update
    point, not adapters scattered across the codebase."""
    assert DEEPSEEK_BASE_URL == "https://api.deepseek.com"
