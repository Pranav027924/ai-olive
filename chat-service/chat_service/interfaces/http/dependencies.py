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

from chat_service.application.ports.llm_client import LLMClient
from chat_service.application.ports.session_repository import SessionRepository
from chat_service.application.use_cases.create_session import CreateSessionHandler
from chat_service.application.use_cases.list_sessions import ListSessionsHandler
from chat_service.application.use_cases.send_text_message import SendTextMessageHandler
from chat_service.config import ChatServiceSettings
from chat_service.domain.services.context_builder import ContextBuilder
from chat_service.infrastructure.persistence.engine import get_sessionmaker
from chat_service.infrastructure.persistence.postgres_session_repo import (
    PostgresSessionRepository,
)
from chat_service.infrastructure.sdk.anthropic_llm_client import AnthropicLLMClient


@lru_cache(maxsize=1)
def _settings() -> ChatServiceSettings:
    return ChatServiceSettings()


def get_settings() -> ChatServiceSettings:
    return _settings()


SettingsDep = Annotated[ChatServiceSettings, Depends(get_settings)]


def get_repository(settings: SettingsDep) -> SessionRepository:
    return PostgresSessionRepository(get_sessionmaker(settings))


RepoDep = Annotated[SessionRepository, Depends(get_repository)]


def get_llm(settings: SettingsDep) -> LLMClient:
    return AnthropicLLMClient(api_key=settings.anthropic_api_key)


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


def get_send_text_message_handler(
    repo: RepoDep, llm: LlmDep, settings: SettingsDep
) -> SendTextMessageHandler:
    return SendTextMessageHandler(
        sessions=repo,
        llm=llm,
        context_builder=ContextBuilder(window=settings.context_window),
    )


CreateSessionDep = Annotated[CreateSessionHandler, Depends(get_create_session_handler)]
ListSessionsDep = Annotated[ListSessionsHandler, Depends(get_list_sessions_handler)]
SendTextMessageDep = Annotated[SendTextMessageHandler, Depends(get_send_text_message_handler)]
