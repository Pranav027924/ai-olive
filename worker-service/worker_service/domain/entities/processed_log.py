"""ProcessedLog — post-redaction, cost-stamped log row (PRD §6.4).

Built from a :class:`LogEvent` plus redacted previews and a recomputed
cost. The PostgresLogRepository inserts one row of ``logs.inference_logs``
per ProcessedLog and one row of ``logs.log_errors`` when ``status="error"``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from contracts.log_event import LogEvent


@dataclass(frozen=True, slots=True)
class ProcessedLog:
    id: UUID
    session_id: UUID
    message_id: UUID | None
    provider: str
    model: str
    status: str
    started_at: datetime
    finished_at: datetime
    latency_ms: int
    ttft_ms: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    input_preview: str
    output_preview: str
    cost_usd: Decimal | None
    raw_metadata: dict[str, Any]
    sdk_version: str
    error_type: str | None = None
    error_message: str | None = None
    http_status: int | None = None
    log_errors_id: UUID | None = field(default=None)

    @property
    def has_error(self) -> bool:
        return self.status == "error" or self.error_type is not None

    @classmethod
    def from_event(
        cls,
        event: LogEvent,
        *,
        redacted_input_preview: str,
        redacted_output_preview: str,
        cost_usd: Decimal | None,
    ) -> ProcessedLog:
        return cls(
            id=event.event_id,
            session_id=event.session_id,
            message_id=event.message_id,
            provider=event.provider,
            model=event.model,
            status=event.status,
            started_at=event.started_at,
            finished_at=event.finished_at,
            latency_ms=event.latency_ms,
            ttft_ms=event.ttft_ms,
            prompt_tokens=event.prompt_tokens,
            completion_tokens=event.completion_tokens,
            input_preview=redacted_input_preview,
            output_preview=redacted_output_preview,
            cost_usd=cost_usd,
            raw_metadata=dict(event.raw_metadata),
            sdk_version=event.sdk_version,
            error_type=event.error_type,
            error_message=event.error_message,
            http_status=event.http_status,
        )
