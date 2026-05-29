"""SdkLlmClient — implements chat-service's LLMClient Protocol using olive-sdk.

Replaces the Phase 1.8 AnthropicLLMClient (Phase 3.10). The SDK owns
the provider adapter and the Tracker that builds + emits a LogEvent
per call; this adapter just maps domain types to SDK types.

One SDK ``LLMClient`` instance is cached per ``(provider, model)``
pair (the SDK ties model + adapter at construction). Both share the
same emitter so every chat call lands in the same JSONL stream
(Phase 3.8) or HTTP batch (Phase 4.8).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from olive_sdk.application.emitter_port import EmitterPort
from olive_sdk.client import LLMClient as SdkLLMClient
from olive_sdk.infrastructure.providers.base_adapter import ChatRole, ChatTurn

from chat_service.application.ports.llm_client import LLMClient
from chat_service.domain.entities.message import Message
from chat_service.domain.value_objects.message_role import MessageRole
from chat_service.domain.value_objects.model_config import ModelConfig

_SDK_ROLE: dict[MessageRole, ChatRole] = {
    MessageRole.USER: "user",
    MessageRole.ASSISTANT: "assistant",
    MessageRole.SYSTEM: "system",
}


class SdkLlmClient(LLMClient):
    def __init__(self, *, emitter: EmitterPort, api_key: str) -> None:
        self._emitter = emitter
        self._api_key = api_key
        self._clients: dict[tuple[str, str], SdkLLMClient] = {}

    async def stream(
        self,
        *,
        session_id: UUID,
        message_id: UUID | None,
        messages: list[Message],
        config: ModelConfig,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        sdk = self._client_for(config)
        sdk_messages = [
            ChatTurn(role=_SDK_ROLE[m.role], content=m.content)
            for m in messages
            if m.role in _SDK_ROLE  # drop MessageRole.TOOL — unused in Phase 1/2/3
        ]
        async for token in sdk.complete(
            session_id=session_id,
            message_id=message_id,
            messages=sdk_messages,
            system_prompt=system_prompt,
        ):
            yield token

    def _client_for(self, config: ModelConfig) -> SdkLLMClient:
        key = (config.provider, config.model)
        if key not in self._clients:
            self._clients[key] = SdkLLMClient(
                provider=config.provider,
                model=config.model,
                emitter=self._emitter,
                api_key=self._api_key,
            )
        return self._clients[key]
