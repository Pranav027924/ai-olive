"""ContextBuilder — rolling window slicing (Phase 1.5)."""

from __future__ import annotations

from uuid import uuid4

from chat_service.domain.entities.session import Session
from chat_service.domain.services.context_builder import DEFAULT_WINDOW, ContextBuilder
from chat_service.domain.value_objects.model_config import ModelConfig


def _session_with_messages(n: int) -> Session:
    s = Session.create(
        user_id=uuid4(), config=ModelConfig(provider="anthropic", model="claude-opus-4-7")
    )
    for i in range(n):
        s.add_user_message(f"u{i}")
        s.add_assistant_message(f"a{i}")
    return s


def test_empty_session_yields_empty_context() -> None:
    s = Session.create(
        user_id=uuid4(), config=ModelConfig(provider="anthropic", model="claude-opus-4-7")
    )
    assert ContextBuilder().build(s) == []


def test_fewer_messages_than_window_returns_all() -> None:
    s = _session_with_messages(3)  # 6 messages
    out = ContextBuilder(window=20).build(s)
    assert out == s.messages


def test_window_returns_last_k_in_order() -> None:
    s = _session_with_messages(5)  # 10 messages, alternating u/a
    out = ContextBuilder(window=4).build(s)

    assert len(out) == 4
    assert [m.content for m in out] == ["u3", "a3", "u4", "a4"]
    # First element of the slice IS messages[-window], not a copy.
    assert out[0] is s.messages[-4]


def test_zero_window_returns_empty() -> None:
    s = _session_with_messages(2)
    assert ContextBuilder(window=0).build(s) == []


def test_negative_window_returns_empty() -> None:
    s = _session_with_messages(2)
    assert ContextBuilder(window=-3).build(s) == []


def test_default_window_is_twenty() -> None:
    assert DEFAULT_WINDOW == 20
    assert ContextBuilder().window == 20


def test_builder_returns_new_list_each_call() -> None:
    """The returned list must not alias the session's internal storage."""
    s = _session_with_messages(2)
    out = ContextBuilder().build(s)
    out.clear()
    assert len(s.messages) == 4
