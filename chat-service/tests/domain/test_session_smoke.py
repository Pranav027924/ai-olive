"""Smoke test for the Session domain (Phase 1.2).

Locks in the public surface of Session, Message, and the relevant value
objects. Detailed invariant / transition tests follow in 1.3.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from chat_service.domain.entities.session import Session
from chat_service.domain.value_objects.message_role import MessageRole
from chat_service.domain.value_objects.message_status import MessageStatus
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.session_status import SessionStatus


def _config() -> ModelConfig:
    return ModelConfig(provider="anthropic", model="claude-opus-4-7")


def test_create_session_starts_active_with_no_messages() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    session = Session.create(user_id=uuid4(), config=_config(), title="hello", now=now)

    assert session.status is SessionStatus.ACTIVE
    assert session.messages == []
    assert session.title == "hello"
    assert session.config.provider == "anthropic"
    assert session.config.model == "claude-opus-4-7"
    assert session.created_at == now
    assert session.updated_at == now


def test_add_user_message_appends_with_seq_one() -> None:
    session = Session.create(user_id=uuid4(), config=_config())

    msg = session.add_user_message("hi")

    assert msg.role is MessageRole.USER
    assert msg.content == "hi"
    assert msg.seq == 1
    assert msg.status is MessageStatus.COMPLETE
    assert session.messages == [msg]


def test_add_assistant_message_increments_seq() -> None:
    session = Session.create(user_id=uuid4(), config=_config())
    session.add_user_message("hi")

    assistant = session.add_assistant_message("hello there")

    assert assistant.role is MessageRole.ASSISTANT
    assert assistant.seq == 2
    assert session.messages[-1] is assistant


def test_add_message_advances_updated_at() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
    session = Session.create(user_id=uuid4(), config=_config(), now=t0)

    session.add_user_message("hi", now=t1)

    assert session.updated_at == t1
