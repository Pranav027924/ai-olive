"""DeepSeekAdapter — DeepSeek via the OpenAI-compatible API (PRD §7.1).

DeepSeek's hosted API exposes the OpenAI Chat Completions wire
format, so this adapter is a thin wrapper around
:class:`OpenAIAdapter` with the base URL pinned to DeepSeek. Pulling
it out as its own class makes the chat-service's provider routing
explicit and lets us add DeepSeek-specific tweaks later (different
default models, custom timeouts) without affecting OpenAI users.
"""

from __future__ import annotations

from openai import AsyncOpenAI

from olive_sdk.infrastructure.providers.openai_adapter import OpenAIAdapter

DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekAdapter(OpenAIAdapter):
    def __init__(
        self,
        *,
        api_key: str = "",
        base_url: str = DEEPSEEK_BASE_URL,
        client: AsyncOpenAI | None = None,
    ) -> None:
        super().__init__(api_key=api_key, base_url=base_url, client=client)
