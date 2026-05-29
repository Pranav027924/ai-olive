"""POST /v1/logs — accept a batch and XADD to Redis Streams (Phase 4.6)."""

from __future__ import annotations

from fastapi import APIRouter, status

from ingestion_service.application.use_cases.ingest_logs import IngestLogsCommand
from ingestion_service.interfaces.http.dependencies import ApiKeyDep, IngestLogsDep
from ingestion_service.interfaces.http.schemas import (
    IngestLogsRequest,
    IngestLogsResponse,
)

router = APIRouter(prefix="/v1", tags=["logs"])


@router.post(
    "/logs",
    response_model=IngestLogsResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_logs(
    body: IngestLogsRequest,
    handler: IngestLogsDep,
    _: ApiKeyDep,
) -> IngestLogsResponse:
    result = await handler.handle(IngestLogsCommand(events=body.events))
    return IngestLogsResponse(
        ingestion_ids=result.ingestion_ids,
        stream_ids=result.stream_ids,
    )
