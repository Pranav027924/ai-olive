"""ContextBuilder — rolling window slicing (Phase 1.5)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from chat_service.domain.entities.attachment import Attachment
from chat_service.domain.entities.session import Session
from chat_service.domain.services.context_builder import DEFAULT_WINDOW, ContextBuilder
from chat_service.domain.value_objects.attachment_kind import AttachmentKind
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.parse_status import ParseStatus


def _attachment(
    *,
    kind: AttachmentKind,
    filename: str,
    parsed_text: str | None = None,
    transcript: str | None = None,
    parse_status: ParseStatus = ParseStatus.COMPLETE,
) -> Attachment:
    return Attachment(
        id=uuid4(),
        session_id=uuid4(),
        kind=kind,
        filename=filename,
        mime_type="application/pdf",
        size_bytes=8,
        s3_key=f"k/{filename}",
        parse_status=parse_status,
        parsed_text=parsed_text,
        transcript=transcript,
        created_at=datetime(2026, 6, 4, tzinfo=UTC),
    )


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


# ---------------------------------------------------------------------------
# compose_system_prompt
# ---------------------------------------------------------------------------


def test_no_attachments_returns_base_prompt_unchanged() -> None:
    assert ContextBuilder().compose_system_prompt("be brief", []) == "be brief"
    assert ContextBuilder().compose_system_prompt(None, []) is None


def test_pending_attachment_is_ignored() -> None:
    pending = _attachment(
        kind=AttachmentKind.FILE,
        filename="r.pdf",
        parse_status=ParseStatus.PENDING,
    )
    assert ContextBuilder().compose_system_prompt("base", [pending]) == "base"


def test_failed_attachment_is_ignored() -> None:
    failed = _attachment(
        kind=AttachmentKind.FILE,
        filename="r.pdf",
        parse_status=ParseStatus.FAILED,
    )
    assert ContextBuilder().compose_system_prompt("base", [failed]) == "base"


def test_complete_pdf_attachment_appended_to_base_prompt() -> None:
    pdf = _attachment(
        kind=AttachmentKind.FILE,
        filename="paper.pdf",
        parsed_text="Hello from the PDF.",
    )

    prompt = ContextBuilder().compose_system_prompt("be brief", [pdf])

    assert prompt is not None
    assert prompt.startswith("be brief")
    assert "Attachment paper.pdf (file):" in prompt
    assert "Hello from the PDF." in prompt


def test_audio_attachment_uses_transcript() -> None:
    audio = _attachment(
        kind=AttachmentKind.AUDIO,
        filename="clip.wav",
        transcript="I said hello world",
    )

    prompt = ContextBuilder().compose_system_prompt(None, [audio])

    assert prompt is not None
    assert "Attachment clip.wav (audio):" in prompt
    assert "I said hello world" in prompt


def test_complete_attachment_without_text_is_skipped() -> None:
    """A complete attachment whose parsed_text/transcript is empty
    contributes nothing — the parse didn't extract anything useful, so
    embedding a heading + empty body would just waste tokens."""
    empty = _attachment(
        kind=AttachmentKind.FILE,
        filename="r.pdf",
        parsed_text=None,
    )
    assert ContextBuilder().compose_system_prompt("base", [empty]) == "base"


def test_multiple_attachments_joined_in_order() -> None:
    a = _attachment(kind=AttachmentKind.FILE, filename="a.pdf", parsed_text="alpha")
    b = _attachment(kind=AttachmentKind.AUDIO, filename="b.wav", transcript="beta")

    prompt = ContextBuilder().compose_system_prompt(None, [a, b])

    assert prompt is not None
    assert prompt.index("Attachment a.pdf") < prompt.index("Attachment b.wav")
    assert "alpha" in prompt
    assert "beta" in prompt
