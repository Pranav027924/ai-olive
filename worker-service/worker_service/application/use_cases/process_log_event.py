"""ProcessLogEvent — the worker's per-event use case (PRD §6.4).

Pipeline::

    if idempotency cache says known          → skip (inserted=False)
    elif repo says event_id already present  → mark cache + skip
    else:
        redact previews                       (RedactionPipeline)
        compute cost                          (CostCalculator)
        build ProcessedLog
        repo.insert(processed)                (Postgres tx)
        mark cache
        → inserted=True

The redaction pipeline and cost calculator are required dependencies
so the application layer stays free of infrastructure imports
(``infrastructure.redaction.regex_redactor.default_pipeline()`` is
wired in by the CLI / DI).
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.log_event import LogEvent

from worker_service.application.ports.log_repository import LogRepository
from worker_service.domain.entities.processed_log import ProcessedLog
from worker_service.domain.services.cost_calculator import CostCalculator
from worker_service.domain.services.idempotency_checker import IdempotencyChecker
from worker_service.domain.services.redaction_pipeline import RedactionPipeline


@dataclass(frozen=True, slots=True)
class ProcessLogEventCommand:
    event: LogEvent


@dataclass(frozen=True, slots=True)
class ProcessLogEventResult:
    inserted: bool
    processed: ProcessedLog | None = None


class ProcessLogEventHandler:
    def __init__(
        self,
        *,
        repo: LogRepository,
        pipeline: RedactionPipeline,
        cost_calculator: CostCalculator,
        idempotency: IdempotencyChecker | None = None,
    ) -> None:
        self._repo = repo
        self._pipeline = pipeline
        self._cost = cost_calculator
        self._idempotency = idempotency or IdempotencyChecker()

    async def handle(self, cmd: ProcessLogEventCommand) -> ProcessLogEventResult:
        event = cmd.event

        if self._idempotency.is_known(event.event_id):
            return ProcessLogEventResult(inserted=False)
        if await self._repo.exists(event.event_id):
            self._idempotency.mark(event.event_id)
            return ProcessLogEventResult(inserted=False)

        input_preview = self._pipeline.redact(event.input_preview)
        output_preview = self._pipeline.redact(event.output_preview)
        cost_usd = self._cost.estimate(
            provider=event.provider,
            model=event.model,
            prompt_tokens=event.prompt_tokens,
            completion_tokens=event.completion_tokens,
        )

        processed = ProcessedLog.from_event(
            event,
            redacted_input_preview=input_preview,
            redacted_output_preview=output_preview,
            cost_usd=cost_usd,
        )
        await self._repo.insert(processed)
        self._idempotency.mark(event.event_id)
        return ProcessLogEventResult(inserted=True, processed=processed)
