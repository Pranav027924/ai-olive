"""PostgresLogRepository — concrete LogRepository (PRD §6.4).

Writes ``logs.inference_logs`` + (when ``has_error``) ``logs.log_errors``
inside one transaction. The PK on inference_logs is ``(id, started_at)``
so a unique-violation only happens on true duplicates — the worker
treats them as "already processed" rather than re-raising.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from worker_service.application.ports.log_repository import LogRepository
from worker_service.domain.entities.processed_log import ProcessedLog
from worker_service.infrastructure.persistence.sqlalchemy_models import (
    InferenceLogRow,
    LogErrorRow,
)


class PostgresLogRepository(LogRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def exists(self, event_id: UUID) -> bool:
        async with self._sessionmaker() as db:
            result = await db.scalar(select(exists().where(InferenceLogRow.id == event_id)))
            return bool(result)

    async def insert(self, processed: ProcessedLog) -> None:
        try:
            async with self._sessionmaker() as db, db.begin():
                db.add(_to_inference_row(processed))
                if processed.has_error:
                    err_id = processed.log_errors_id or uuid4()
                    db.add(
                        LogErrorRow(
                            id=err_id,
                            log_id=processed.id,
                            error_type=processed.error_type or "Unknown",
                            error_message=processed.error_message,
                            http_status=processed.http_status,
                        )
                    )
        except IntegrityError:
            # Concurrent worker already wrote this row; treat as success.
            return


def _to_inference_row(processed: ProcessedLog) -> InferenceLogRow:
    return InferenceLogRow(
        id=processed.id,
        session_id=processed.session_id,
        message_id=processed.message_id,
        provider=processed.provider,
        model=processed.model,
        status=processed.status,
        started_at=processed.started_at,
        finished_at=processed.finished_at,
        latency_ms=processed.latency_ms,
        ttft_ms=processed.ttft_ms,
        prompt_tokens=processed.prompt_tokens,
        completion_tokens=processed.completion_tokens,
        input_preview=processed.input_preview,
        output_preview=processed.output_preview,
        cost_usd=processed.cost_usd,
        raw_metadata=processed.raw_metadata,
        sdk_version=processed.sdk_version,
    )
