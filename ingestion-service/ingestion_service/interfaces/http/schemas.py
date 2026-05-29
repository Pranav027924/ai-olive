"""Pydantic wire models for the ingestion HTTP API (Phase 4.6)."""

from __future__ import annotations

from uuid import UUID

from contracts.log_event import LogEvent
from pydantic import BaseModel, ConfigDict


class IngestLogsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[LogEvent]


class IngestLogsResponse(BaseModel):
    ingestion_ids: list[UUID]
    stream_ids: list[str]


class ProblemDetail(BaseModel):
    """RFC 7807 problem details (PRD §9.6)."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
