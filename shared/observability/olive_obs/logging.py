"""structlog configuration (PRD §9.1).

``configure_logging`` is called once per process at startup. It wires
stdlib ``logging`` through structlog so libraries that use the stdlib
logger (uvicorn, sqlalchemy, redis) emit the same structured JSON,
and binds the service name onto every event. ``merge_contextvars``
pulls in anything bound by the request-id middleware so each line
carries its ``request_id``.
"""

from __future__ import annotations

import logging
import sys

import structlog

_configured = False


def configure_logging(
    *,
    service: str,
    level: str = "INFO",
    json_logs: bool = True,
) -> None:
    """Idempotently configure structlog + stdlib logging for ``service``."""
    global _configured

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _add_service(service),
    ]

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level) if isinstance(level, str) else level
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging through the same renderer so third-party
    # libraries don't break the JSON stream.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
            foreign_pre_chain=shared_processors,
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    _configured = True


def _add_service(service: str) -> structlog.typing.Processor:
    def processor(
        _logger: object, _method: str, event_dict: structlog.typing.EventDict
    ) -> structlog.typing.EventDict:
        event_dict.setdefault("service", service)
        return event_dict

    return processor


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


def is_configured() -> bool:
    return _configured
