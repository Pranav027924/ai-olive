"""Tests for the StreamingResponse value object (Phase 2.1).

Locks in the state machine and the terminal-state invariants. The
application layer in Phase 2.2 builds on these guarantees.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from chat_service.domain.errors import InvalidStreamState
from chat_service.domain.value_objects.streaming_response import (
    StreamingResponse,
    StreamingState,
)


def _new() -> StreamingResponse:
    return StreamingResponse(session_id=uuid4(), message_id=uuid4())


# ---------------------------------------------------------------------------
# Creation defaults
# ---------------------------------------------------------------------------


def test_starts_active_with_empty_content() -> None:
    s = _new()
    assert s.state is StreamingState.ACTIVE
    assert s.content == ""
    assert s.is_terminal is False


# ---------------------------------------------------------------------------
# push() accumulates and is order-preserving
# ---------------------------------------------------------------------------


def test_push_appends_chunks_in_order() -> None:
    s = _new()
    s.push("hel")
    s.push("lo ")
    s.push("world")
    assert s.content == "hello world"


def test_push_after_terminal_raises() -> None:
    s = _new()
    s.complete()
    with pytest.raises(InvalidStreamState):
        s.push("late")


def test_push_after_cancel_raises() -> None:
    s = _new()
    s.cancel()
    with pytest.raises(InvalidStreamState):
        s.push("late")


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


def test_complete_marks_completed() -> None:
    s = _new()
    s.push("hi")
    s.complete()
    assert s.state is StreamingState.COMPLETED
    assert s.is_terminal is True
    assert s.content == "hi"


def test_cancel_marks_cancelled_and_preserves_partial_content() -> None:
    s = _new()
    s.push("partial ")
    s.push("answer")
    s.cancel()
    assert s.state is StreamingState.CANCELLED
    assert s.is_terminal is True
    assert s.content == "partial answer"


def test_error_marks_errored() -> None:
    s = _new()
    s.push("oh")
    s.error()
    assert s.state is StreamingState.ERRORED
    assert s.is_terminal is True
    assert s.content == "oh"


@pytest.mark.parametrize(
    ("first", "second_action"),
    [
        ("complete", "complete"),
        ("complete", "cancel"),
        ("complete", "error"),
        ("cancel", "cancel"),
        ("cancel", "complete"),
        ("cancel", "error"),
        ("error", "error"),
        ("error", "complete"),
        ("error", "cancel"),
    ],
)
def test_terminal_state_is_terminal(first: str, second_action: str) -> None:
    s = _new()
    getattr(s, first)()
    with pytest.raises(InvalidStreamState):
        getattr(s, second_action)()
