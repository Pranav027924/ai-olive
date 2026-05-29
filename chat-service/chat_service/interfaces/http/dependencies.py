"""FastAPI dependency providers.

Wire ports to their concrete adapters (Postgres repo, Anthropic LLM
client). The handlers themselves are constructed per-request from
those adapters.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from olive_sdk.application.emitter_port import EmitterPort
from olive_sdk.infrastructure.emitters.composite_emitter import CompositeEmitter
from olive_sdk.infrastructure.emitters.file_emitter import FileEmitter
from olive_sdk.infrastructure.emitters.http_emitter import HttpEmitter
from redis.asyncio import Redis

from chat_service.application.ports.cancellation_store import CancellationStore
from chat_service.application.ports.llm_client import LLMClient
from chat_service.application.ports.session_repository import SessionRepository
from chat_service.application.use_cases.cancel_stream import CancelStreamHandler
from chat_service.application.use_cases.create_session import CreateSessionHandler
from chat_service.application.use_cases.list_sessions import ListSessionsHandler
from chat_service.application.use_cases.send_text_message import SendTextMessageHandler
from chat_service.application.use_cases.stream_assistant_response import (
    StreamAssistantResponseHandler,
)
from chat_service.config import ChatServiceSettings
from chat_service.domain.services.context_builder import ContextBuilder
from chat_service.infrastructure.cache.redis_cancellation_store import (
    RedisCancellationStore,
)
from chat_service.infrastructure.persistence.engine import get_sessionmaker
from chat_service.infrastructure.persistence.postgres_session_repo import (
    PostgresSessionRepository,
)
from chat_service.infrastructure.sdk.sdk_llm_client import SdkLlmClient


@lru_cache(maxsize=1)
def _settings() -> ChatServiceSettings:
    return ChatServiceSettings()


def get_settings() -> ChatServiceSettings:
    return _settings()


SettingsDep = Annotated[ChatServiceSettings, Depends(get_settings)]


def get_repository(settings: SettingsDep) -> SessionRepository:
    return PostgresSessionRepository(get_sessionmaker(settings))


RepoDep = Annotated[SessionRepository, Depends(get_repository)]


@lru_cache(maxsize=1)
def _sdk_emitter() -> EmitterPort:
    """Build the chat-service's emitter.

    When ``ingestion_url`` is set we tee to both an HttpEmitter (for
    analytics via the ingestion service → Redis Streams → Worker) and
    a FileEmitter (so devs can ``tail -f logs/inference.jsonl``). With
    no ingestion URL configured we degrade to file-only so the SDK
    still produces output for inspection.
    """
    settings = _settings()
    file_emitter = FileEmitter(path=settings.log_emitter_path)
    if not settings.ingestion_url:
        return file_emitter
    http_emitter = HttpEmitter(
        endpoint=settings.ingestion_url,
        api_key=settings.ingestion_api_key,
        max_batch=settings.http_emitter_max_batch,
        flush_interval_seconds=settings.http_emitter_flush_interval_seconds,
        queue_size=settings.http_emitter_queue_size,
    )
    return CompositeEmitter(emitters=[http_emitter, file_emitter])


@lru_cache(maxsize=1)
def _sdk_llm_client() -> SdkLlmClient:
    settings = _settings()
    return SdkLlmClient(emitter=_sdk_emitter(), api_key=settings.anthropic_api_key)


def get_llm(settings: SettingsDep) -> LLMClient:
    return _sdk_llm_client()


LlmDep = Annotated[LLMClient, Depends(get_llm)]


def get_dev_user_id(settings: SettingsDep) -> UUID:
    """Dev-only stand-in for the authenticated user (PRD §9.5)."""
    return settings.dev_user_id


CurrentUserDep = Annotated[UUID, Depends(get_dev_user_id)]


# ---------------------------------------------------------------------------
# Use-case handler dependencies
# ---------------------------------------------------------------------------


def get_create_session_handler(repo: RepoDep) -> CreateSessionHandler:
    return CreateSessionHandler(sessions=repo)


def get_list_sessions_handler(repo: RepoDep) -> ListSessionsHandler:
    return ListSessionsHandler(sessions=repo)


@lru_cache(maxsize=1)
def _redis_client() -> Redis:
    return Redis.from_url(_settings().redis_url, decode_responses=True)


def get_cancellations(settings: SettingsDep) -> CancellationStore:
    return RedisCancellationStore(
        redis=_redis_client(),
        ttl_seconds=settings.cancel_ttl_seconds,
    )


CancellationsDep = Annotated[CancellationStore, Depends(get_cancellations)]


def get_send_text_message_handler(repo: RepoDep) -> SendTextMessageHandler:
    return SendTextMessageHandler(sessions=repo)


def get_stream_assistant_response_handler(
    repo: RepoDep, llm: LlmDep, cancellations: CancellationsDep, settings: SettingsDep
) -> StreamAssistantResponseHandler:
    return StreamAssistantResponseHandler(
        sessions=repo,
        llm=llm,
        cancellations=cancellations,
        context_builder=ContextBuilder(window=settings.context_window),
    )


def get_cancel_stream_handler(
    repo: RepoDep, cancellations: CancellationsDep
) -> CancelStreamHandler:
    return CancelStreamHandler(sessions=repo, cancellations=cancellations)


CreateSessionDep = Annotated[CreateSessionHandler, Depends(get_create_session_handler)]
ListSessionsDep = Annotated[ListSessionsHandler, Depends(get_list_sessions_handler)]
SendTextMessageDep = Annotated[SendTextMessageHandler, Depends(get_send_text_message_handler)]
StreamAssistantResponseDep = Annotated[
    StreamAssistantResponseHandler, Depends(get_stream_assistant_response_handler)
]
CancelStreamDep = Annotated[CancelStreamHandler, Depends(get_cancel_stream_handler)]
