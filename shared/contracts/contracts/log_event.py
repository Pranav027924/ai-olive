"""LogEvent — the canonical inference observation shared across services.

PRD §7.1 is the source of truth for this schema. LogEvent is the wire format
used in:

- HTTP POST bodies from the Logging SDK to the Ingestion service.
- JSON payloads in the ``inference_logs`` Redis Stream between Ingestion and
  Worker.

It is a value object: immutable (``frozen=True``), strictly validated
(``extra="forbid"``), and identified for idempotency by ``event_id``. The
Worker enforces exactly-once-effective semantics by deduping on this id.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Provider = Literal["openai", "anthropic", "gemini", "deepseek"]
"""LLM providers we have adapters for. See PRD §2.1, §7.1."""

Status = Literal["success", "error", "cancelled", "timeout"]
"""Terminal outcomes for a single inference attempt. See PRD §2.2, §7.1."""

PREVIEW_MAX_LENGTH = 500
"""Maximum length, in characters, for ``input_preview`` and ``output_preview``.

Previews are truncated at the SDK boundary before the LogEvent is built.
PRD §2.2: "input/output previews (truncated)".
"""


class LogEvent(BaseModel):
    """A single LLM inference observation, captured by the SDK.

    The SDK builds one LogEvent per call (success, error, cancel, or timeout)
    and ships it to the Ingestion service. The Worker persists it to Postgres
    (`logs.inference_logs`) and forwards a metric row to ClickHouse.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=False,
    )

    event_id: UUID = Field(
        description="Idempotency key. Two events with this id must be treated as duplicates.",
    )
    session_id: UUID
    message_id: UUID | None = Field(
        default=None,
        description="None when the inference errored before a message row was created.",
    )

    provider: Provider
    model: str
    status: Status

    started_at: datetime
    finished_at: datetime
    latency_ms: int = Field(ge=0)
    ttft_ms: int | None = Field(default=None, ge=0)

    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)

    input_preview: str = Field(max_length=PREVIEW_MAX_LENGTH)
    output_preview: str = Field(max_length=PREVIEW_MAX_LENGTH)

    error_type: str | None = None
    error_message: str | None = None
    http_status: int | None = None

    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    sdk_version: str
