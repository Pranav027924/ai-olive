"""AnthropicLLMClient — direct Anthropic adapter for the LLMClient port.

Phase 1 uses Anthropic's blocking ``messages.create`` API; Phase 2
replaces this with the streaming variant, and Phase 3 wraps it again
through the logging SDK without changing the application layer
(PRD §6.1, §6.2).

Notes:
- Anthropic only accepts ``user`` and ``assistant`` roles in the
  ``messages`` list. ``system`` is passed via the separate ``system``
  parameter; any ``system`` messages in the context are dropped here.
- ``tool`` messages are not used in Phase 1 and are also filtered out.
"""

from __future__ import annotations

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, TextBlock

from chat_service.application.ports.llm_client import LLMClient
from chat_service.domain.entities.message import Message
from chat_service.domain.value_objects.message_role import MessageRole
from chat_service.domain.value_objects.model_config import ModelConfig

DEFAULT_MAX_TOKENS = 4096


class AnthropicLLMClient(LLMClient):
    def __init__(
        self,
        *,
        api_key: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        client: AsyncAnthropic | None = None,
    ) -> None:
        self._client = client or AsyncAnthropic(api_key=api_key)
        self._max_tokens = max_tokens

    async def complete(
        self,
        *,
        messages: list[Message],
        config: ModelConfig,
        system_prompt: str | None = None,
    ) -> str:
        anthropic_messages: list[MessageParam] = [
            {
                "role": "user" if m.role is MessageRole.USER else "assistant",
                "content": m.content,
            }
            for m in messages
            if m.role in (MessageRole.USER, MessageRole.ASSISTANT)
        ]

        if system_prompt:
            response = await self._client.messages.create(
                model=config.model,
                max_tokens=self._max_tokens,
                messages=anthropic_messages,
                system=system_prompt,
            )
        else:
            response = await self._client.messages.create(
                model=config.model,
                max_tokens=self._max_tokens,
                messages=anthropic_messages,
            )

        for block in response.content:
            if isinstance(block, TextBlock):
                return block.text
        return ""
