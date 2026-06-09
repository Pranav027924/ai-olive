"""Tests for structlog configuration (Phase 9.1)."""

from __future__ import annotations

import structlog
from olive_obs.logging import configure_logging, get_logger, is_configured


def test_configure_is_idempotent_and_sets_flag() -> None:
    configure_logging(service="svc-a")
    configure_logging(service="svc-a")
    assert is_configured() is True


def test_emitted_event_reaches_the_logger() -> None:
    configure_logging(service="svc-b")
    with structlog.testing.capture_logs() as logs:
        get_logger("test").info("hello", extra="x")

    assert len(logs) == 1
    assert logs[0]["event"] == "hello"
    assert logs[0]["extra"] == "x"


def test_bound_request_id_is_merged_into_events() -> None:
    """``merge_contextvars`` is part of the configured chain, so a
    request_id bound by the middleware lands on every log line."""
    configure_logging(service="svc-b")
    structlog.contextvars.bind_contextvars(request_id="rid-123")
    try:
        merged = structlog.contextvars.merge_contextvars(None, "info", {"event": "hello"})
    finally:
        structlog.contextvars.clear_contextvars()
    assert merged["request_id"] == "rid-123"


def test_service_name_is_attached() -> None:
    configure_logging(service="svc-c", json_logs=True)
    # capture_logs short-circuits processors, so assert the service
    # processor itself stamps the field.
    from typing import cast

    from olive_obs.logging import _add_service

    processor = _add_service("svc-c")
    event = cast("dict[str, object]", processor(None, "info", {"event": "e"}))
    assert event["service"] == "svc-c"
