"""Comprehensive behaviour tests for the Session aggregate (Phase 1.3).

Covers:
- creation defaults (ids, status, timestamps)
- seq monotonicity across mixed user/assistant messages
- status transitions: every allowed pair, every disallowed pair
- terminal-status invariant: no appends after ARCHIVED / DELETED
- value-object equality (ModelConfig)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import product
from uuid import UUID, uuid4

import pytest
from chat_service.domain.entities.session import Session
from chat_service.domain.errors import InvalidStatusTransition, SessionAlreadyTerminal
from chat_service.domain.value_objects.message_role import MessageRole
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.session_status import SessionStatus

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_CONFIG = ModelConfig(provider="anthropic", model="claude-opus-4-7")
_T0 = datetime(2026, 1, 1, tzinfo=UTC)

_ALLOWED: dict[SessionStatus, frozenset[SessionStatus]] = {
    SessionStatus.ACTIVE: frozenset(
        {
            SessionStatus.CANCELLED,
            SessionStatus.COMPLETED,
            SessionStatus.ARCHIVED,
            SessionStatus.DELETED,
        }
    ),
    SessionStatus.CANCELLED: frozenset({SessionStatus.ARCHIVED, SessionStatus.DELETED}),
    SessionStatus.COMPLETED: frozenset({SessionStatus.ARCHIVED, SessionStatus.DELETED}),
    SessionStatus.ARCHIVED: frozenset({SessionStatus.DELETED}),
    SessionStatus.DELETED: frozenset(),
}


def _new(now: datetime = _T0) -> Session:
    return Session.create(user_id=uuid4(), config=_CONFIG, now=now)


def _force_status(session: Session, target: SessionStatus) -> None:
    """Walk through allowed transitions to reach ``target`` for test setup."""
    if session.status is target:
        return
    if target in _ALLOWED[session.status]:
        session.transition_to(target)
        return
    # Two-hop walks cover every reachable target from ACTIVE in this domain.
    for intermediate in _ALLOWED[session.status]:
        if target in _ALLOWED[intermediate]:
            session.transition_to(intermediate)
            session.transition_to(target)
            return
    raise AssertionError(f"cannot reach {target} from {session.status} in test setup")


# ---------------------------------------------------------------------------
# Creation defaults
# ---------------------------------------------------------------------------


def test_create_assigns_random_uuid_when_session_id_not_given() -> None:
    a = _new()
    b = _new()
    assert isinstance(a.id, UUID)
    assert isinstance(b.id, UUID)
    assert a.id != b.id


def test_create_honors_supplied_session_id() -> None:
    sid = uuid4()
    session = Session.create(user_id=uuid4(), config=_CONFIG, session_id=sid)
    assert session.id == sid


def test_create_with_no_now_uses_utc_clock() -> None:
    before = datetime.now(UTC)
    session = _new(now=None)  # type: ignore[arg-type]
    after = datetime.now(UTC)
    assert before <= session.created_at <= after
    assert session.created_at == session.updated_at
    assert session.created_at.tzinfo is UTC


def test_create_with_no_now_uses_utc_clock_explicit() -> None:
    # Mirror of the above without bypassing the keyword default — exercises
    # the public API as a caller would write it.
    before = datetime.now(UTC)
    session = Session.create(user_id=uuid4(), config=_CONFIG)
    after = datetime.now(UTC)
    assert before <= session.created_at <= after


# ---------------------------------------------------------------------------
# seq monotonicity
# ---------------------------------------------------------------------------


def test_seq_increments_one_by_one_across_roles() -> None:
    session = _new()
    user_a = session.add_user_message("a")
    asst_a = session.add_assistant_message("A")
    user_b = session.add_user_message("b")
    asst_b = session.add_assistant_message("B")

    assert [m.seq for m in session.messages] == [1, 2, 3, 4]
    assert [m.role for m in session.messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    # IDs are distinct
    assert len({user_a.id, asst_a.id, user_b.id, asst_b.id}) == 4


def test_message_ids_can_be_injected_for_determinism() -> None:
    session = _new()
    mid = uuid4()
    msg = session.add_user_message("hi", message_id=mid)
    assert msg.id == mid


# ---------------------------------------------------------------------------
# updated_at advances on mutation; created_at is fixed
# ---------------------------------------------------------------------------


def test_updated_at_advances_on_message_append() -> None:
    session = _new(now=_T0)
    later = _T0 + timedelta(minutes=5)
    session.add_user_message("hi", now=later)
    assert session.created_at == _T0
    assert session.updated_at == later


def test_updated_at_advances_on_status_transition() -> None:
    session = _new(now=_T0)
    later = _T0 + timedelta(minutes=10)
    session.transition_to(SessionStatus.COMPLETED, now=later)
    assert session.created_at == _T0
    assert session.updated_at == later


# ---------------------------------------------------------------------------
# Status transitions — exhaustive over the cross product
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("frm", "to"),
    [(f, t) for f, ts in _ALLOWED.items() for t in ts],
)
def test_every_allowed_transition_is_permitted(frm: SessionStatus, to: SessionStatus) -> None:
    session = _new()
    _force_status(session, frm)
    session.transition_to(to)
    assert session.status is to


@pytest.mark.parametrize(
    ("frm", "to"),
    [
        (f, t)
        for f, t in product(SessionStatus, SessionStatus)
        if t not in _ALLOWED[f] and f is not t
    ],
)
def test_every_disallowed_transition_raises(frm: SessionStatus, to: SessionStatus) -> None:
    session = _new()
    _force_status(session, frm)
    with pytest.raises(InvalidStatusTransition) as exc:
        session.transition_to(to)
    assert exc.value.frm is frm
    assert exc.value.to is to


def test_self_transition_is_disallowed() -> None:
    session = _new()
    with pytest.raises(InvalidStatusTransition):
        session.transition_to(SessionStatus.ACTIVE)


# ---------------------------------------------------------------------------
# Terminal-status invariant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("terminal", [SessionStatus.ARCHIVED, SessionStatus.DELETED])
def test_cannot_append_user_message_after_terminal(terminal: SessionStatus) -> None:
    session = _new()
    _force_status(session, terminal)
    with pytest.raises(SessionAlreadyTerminal) as exc:
        session.add_user_message("nope")
    assert exc.value.status is terminal


@pytest.mark.parametrize("terminal", [SessionStatus.ARCHIVED, SessionStatus.DELETED])
def test_cannot_append_assistant_message_after_terminal(terminal: SessionStatus) -> None:
    session = _new()
    _force_status(session, terminal)
    with pytest.raises(SessionAlreadyTerminal):
        session.add_assistant_message("nope")


def test_cancelled_session_still_accepts_no_new_messages_only_via_terminal_check() -> None:
    """Cancelled is non-terminal in this domain — appends still allowed.

    Documents the current intent: cancellation is the user pressing the
    cancel button mid-stream and partial output is saved (PRD §4.4).
    The session itself is not yet archived/deleted.
    """
    session = _new()
    session.transition_to(SessionStatus.CANCELLED)
    msg = session.add_assistant_message("partial")
    assert msg.seq == 1


# ---------------------------------------------------------------------------
# Value-object equality
# ---------------------------------------------------------------------------


def test_model_config_equality_is_by_value() -> None:
    a = ModelConfig(provider="anthropic", model="claude-opus-4-7")
    b = ModelConfig(provider="anthropic", model="claude-opus-4-7")
    c = ModelConfig(provider="anthropic", model="claude-sonnet-4-6")
    assert a == b
    assert a != c
    assert hash(a) == hash(b)


def test_model_config_is_frozen() -> None:
    cfg = ModelConfig(provider="anthropic", model="claude-opus-4-7")
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError subclass varies
        cfg.provider = "openai"  # type: ignore[misc]
