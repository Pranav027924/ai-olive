"""Tracker — async context manager that builds a LogEvent (PRD §6.2).

A LogEvent is built on every exit path (success, error, cancel, or
timeout) and shipped to the configured EmitterPort. Use::

    tracker = Tracker(
        emitter=emitter,
        session_id=session_id,
        message_id=message_id,
        provider="anthropic",
        model="claude-opus-4-7",
        sdk_version="0.1.0",
        input_preview="hi there",
    )
    async with tracker:
        async for evt in adapter.stream(...):
            if isinstance(evt, ChunkEvent):
                tracker.record_chunk(evt.text)
                yield evt.text
            elif isinstance(evt, UsageEvent):
                tracker.record_usage(evt.prompt_tokens, evt.completion_tokens)
        # if the caller decided to cancel:
        #   tracker.mark_cancelled()
    # LogEvent is emitted automatically here.

If the body raises, the resulting LogEvent has status="error" and
carries the exception type + message. The exception is *not*
suppressed.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self
from uuid import UUID, uuid4

from contracts.log_event import PREVIEW_MAX_LENGTH, LogEvent, Status

from olive_sdk.application.emitter_port import EmitterPort


def _now() -> datetime:
    return datetime.now(UTC)


def _truncate(text: str, *, limit: int = PREVIEW_MAX_LENGTH) -> str:
    return text if len(text) <= limit else text[:limit]


class Tracker:
    """Builds and ships a single LogEvent across the lifetime of one LLM call."""

    def __init__(
        self,
        *,
        emitter: EmitterPort,
        session_id: UUID,
        provider: str,
        model: str,
        sdk_version: str,
        message_id: UUID | None = None,
        event_id: UUID | None = None,
        input_preview: str = "",
        raw_metadata: dict[str, Any] | None = None,
    ) -> None:
        self._emitter = emitter
        self._event_id: UUID = event_id or uuid4()
        self._session_id = session_id
        self._message_id = message_id
        self._provider = provider
        self._model = model
        self._sdk_version = sdk_version
        self._input_preview = _truncate(input_preview)
        self._raw_metadata: dict[str, Any] = dict(raw_metadata or {})

        self._started_at: datetime | None = None
        self._first_chunk_at: datetime | None = None
        self._chunks: list[str] = []
        self._prompt_tokens: int | None = None
        self._completion_tokens: int | None = None
        self._explicit_status: Status | None = None

    # ------------------------------------------------------------------
    # Recording hooks (called from inside the `async with` block)
    # ------------------------------------------------------------------

    def record_chunk(self, text: str) -> None:
        if self._first_chunk_at is None:
            self._first_chunk_at = _now()
        self._chunks.append(text)

    def record_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens

    def mark_cancelled(self) -> None:
        self._explicit_status = "cancelled"

    def mark_timeout(self) -> None:
        self._explicit_status = "timeout"

    def add_metadata(self, **fields: Any) -> None:
        self._raw_metadata.update(fields)

    @property
    def event_id(self) -> UUID:
        return self._event_id

    # ------------------------------------------------------------------
    # Context-manager lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self) -> Self:
        self._started_at = _now()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        finished_at = _now()
        started_at = self._started_at or finished_at
        latency_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
        ttft_ms = (
            None
            if self._first_chunk_at is None
            else max(0, int((self._first_chunk_at - started_at).total_seconds() * 1000))
        )

        # Status precedence:
        #   1. asyncio.CancelledError → cancelled (so cooperative cancel
        #      from the host event loop is reflected without the caller
        #      having to call mark_cancelled()).
        #   2. Any other exception → error.
        #   3. Explicit mark_cancelled / mark_timeout.
        #   4. Otherwise success.
        if exc_type is not None and issubclass(exc_type, asyncio.CancelledError):
            status: Status = "cancelled"
            error_type: str | None = None
            error_message: str | None = None
        elif exc_type is not None:
            status = "error"
            error_type = exc_type.__name__
            error_message = str(exc_val) if exc_val is not None else None
        elif self._explicit_status is not None:
            status = self._explicit_status
            error_type = None
            error_message = None
        else:
            status = "success"
            error_type = None
            error_message = None

        event = LogEvent(
            event_id=self._event_id,
            session_id=self._session_id,
            message_id=self._message_id,
            provider=self._provider,  # type: ignore[arg-type]
            model=self._model,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=latency_ms,
            ttft_ms=ttft_ms,
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
            input_preview=self._input_preview,
            output_preview=_truncate("".join(self._chunks)),
            error_type=error_type,
            error_message=error_message,
            raw_metadata=self._raw_metadata,
            sdk_version=self._sdk_version,
        )
        await self._emitter.emit(event)
