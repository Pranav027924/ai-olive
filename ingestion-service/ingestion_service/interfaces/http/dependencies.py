"""FastAPI dependency providers for the ingestion service (Phase 4.6)."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from redis.asyncio import Redis

from ingestion_service.application.ports.auth_provider import AuthProvider
from ingestion_service.application.ports.log_stream import LogStream
from ingestion_service.application.use_cases.ingest_logs import IngestLogsHandler
from ingestion_service.config import IngestionSettings
from ingestion_service.infrastructure.auth.api_key_auth import ApiKeyAuthProvider
from ingestion_service.infrastructure.streams.redis_stream import RedisStreamAdapter


@lru_cache(maxsize=1)
def _settings() -> IngestionSettings:
    return IngestionSettings()


def get_settings() -> IngestionSettings:
    return _settings()


SettingsDep = Annotated[IngestionSettings, Depends(get_settings)]


@lru_cache(maxsize=1)
def _redis_client() -> Redis:
    return Redis.from_url(_settings().redis_url, decode_responses=True)


def get_log_stream(settings: SettingsDep) -> LogStream:
    return RedisStreamAdapter(
        redis=_redis_client(),
        stream=settings.stream_name,
        maxlen=settings.stream_maxlen,
    )


LogStreamDep = Annotated[LogStream, Depends(get_log_stream)]


def get_ingest_logs_handler(stream: LogStreamDep) -> IngestLogsHandler:
    return IngestLogsHandler(stream=stream)


IngestLogsDep = Annotated[IngestLogsHandler, Depends(get_ingest_logs_handler)]


@lru_cache(maxsize=1)
def _auth_provider() -> AuthProvider:
    return ApiKeyAuthProvider(expected_key=_settings().ingestion_api_key)


def get_auth_provider() -> AuthProvider:
    return _auth_provider()


def require_api_key(
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    x_api_key: Annotated[str | None, Header(alias="x-api-key")] = None,
) -> None:
    if not x_api_key or not auth.is_valid(x_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing x-api-key",
        )


ApiKeyDep = Annotated[None, Depends(require_api_key)]
