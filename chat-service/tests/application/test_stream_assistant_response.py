"""Exhaustive tests for StreamAssistantResponseHandler (Phase 2.3)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from chat_service.application.use_cases.create_session import (
    CreateSessionCommand,
    CreateSessionHandler,
)
from chat_service.application.use_cases.send_text_message import (
    SendTextMessageCommand,
    SendTextMessageHandler,
)
from chat_service.application.use_cases.stream_assistant_response import (
    StreamAssistantResponseCommand,
    StreamAssistantResponseHandler,
    StreamChunk,
    StreamFinished,
    StreamStarted,
)
from chat_service.domain.errors import SessionAlreadyTerminal, SessionNotFound
from chat_service.domain.services.context_builder import ContextBuilder
from chat_service.domain.value_objects.message_role import MessageRole
from chat_service.domain.value_objects.message_status import MessageStatus
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.session_status import SessionStatus
from chat_service.domain.value_objects.streaming_response import StreamingState

from tests.conftest import (
    FakeLLMClient,
    InMemoryCancellationStore,
    InMemorySessionRepository,
)


async def _make_session_with_user_message(
    repo: InMemorySessionRepository, config: ModelConfig, content: str = "hi"
) -> object:
    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(CreateSessionCommand(user_id=uuid4(), config=config))
    await SendTextMessageHandler(sessions=repo).handle(
        SendTextMessageCommand(session_id=session.id, content=content)
    )
    return session


async def _collect(handler: StreamAssistantResponseHandler, session_id: object) -> list[object]:
    return [
        e
        async for e in handler.handle(
            StreamAssistantResponseCommand(session_id=session_id)  # type: ignore[arg-type]
        )
    ]


async def _exhaust(handler: StreamAssistantResponseHandler, session_id: object) -> None:
    """Drive the async generator to completion; used inside pytest.raises blocks."""
    async for _ in handler.handle(
        StreamAssistantResponseCommand(session_id=session_id)  # type: ignore[arg-type]
    ):
        raise AssertionError("no event should be yielded")


# ---------------------------------------------------------------------------
# Event ordering and shape
# ---------------------------------------------------------------------------


async def test_started_chunks_finished_event_sequence(
    repo: InMemorySessionRepository, llm: FakeLLMClient, config: ModelConfig
) -> None:
    llm.chunks = ["a", "b", "c"]
    session = await _make_session_with_user_message(repo, config)

    events = await _collect(
        StreamAssistantResponseHandler(sessions=repo, llm=llm),
        session.id,  # type: ignore[attr-defined]
    )

    assert len(events) == 5
    assert isinstance(events[0], StreamStarted)
    assert all(isinstance(e, StreamChunk) for e in events[1:4])
    assert isinstance(events[4], StreamFinished)


async def test_started_carries_pre_generated_message_id_and_seq(
    repo: InMemorySessionRepository, llm: FakeLLMClient, config: ModelConfig
) -> None:
    session = await _make_session_with_user_message(repo, config)

    events = await _collect(
        StreamAssistantResponseHandler(sessions=repo, llm=llm),
        session.id,  # type: ignore[attr-defined]
    )

    started = events[0]
    finished = events[-1]
    assert isinstance(started, StreamStarted)
    assert isinstance(finished, StreamFinished)
    assert started.assistant_message_id == finished.message.id
    assert started.seq == 2  # user msg was seq=1


# ---------------------------------------------------------------------------
# Persistence + status mapping
# ---------------------------------------------------------------------------


async def test_completed_persists_assistant_message_with_status_complete(
    repo: InMemorySessionRepository, llm: FakeLLMClient, config: ModelConfig
) -> None:
    llm.chunks = ["hel", "lo"]
    session = await _make_session_with_user_message(repo, config)

    events = await _collect(
        StreamAssistantResponseHandler(sessions=repo, llm=llm),
        session.id,  # type: ignore[attr-defined]
    )

    finished = events[-1]
    assert isinstance(finished, StreamFinished)
    assert finished.state is StreamingState.COMPLETED
    assert finished.content == "hello"
    assert finished.message.status is MessageStatus.COMPLETE
    assert finished.error is None

    persisted = await repo.get(session.id)  # type: ignore[attr-defined]
    assert persisted is not None
    assert [m.content for m in persisted.messages] == ["hi", "hello"]


async def test_empty_stream_still_completes_with_empty_content(
    repo: InMemorySessionRepository, llm: FakeLLMClient, config: ModelConfig
) -> None:
    llm.chunks = []
    session = await _make_session_with_user_message(repo, config)

    events = await _collect(
        StreamAssistantResponseHandler(sessions=repo, llm=llm),
        session.id,  # type: ignore[attr-defined]
    )

    assert [type(e).__name__ for e in events] == ["StreamStarted", "StreamFinished"]
    finished = events[-1]
    assert isinstance(finished, StreamFinished)
    assert finished.state is StreamingState.COMPLETED
    assert finished.content == ""


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------


async def test_llm_error_after_some_chunks_finishes_errored_with_partial_content(
    repo: InMemorySessionRepository, config: ModelConfig
) -> None:
    llm = FakeLLMClient(chunks=["partial "], error=RuntimeError("provider on fire"))
    session = await _make_session_with_user_message(repo, config)

    events = await _collect(
        StreamAssistantResponseHandler(sessions=repo, llm=llm),
        session.id,  # type: ignore[attr-defined]
    )

    # The StreamChunk for "partial " is yielded before the error.
    chunks = [e for e in events if isinstance(e, StreamChunk)]
    assert [c.text for c in chunks] == ["partial "]

    finished = events[-1]
    assert isinstance(finished, StreamFinished)
    assert finished.state is StreamingState.ERRORED
    assert finished.content == "partial "
    assert finished.message.status is MessageStatus.ERROR
    assert finished.error is not None
    assert "RuntimeError" in finished.error
    assert "provider on fire" in finished.error


async def test_llm_error_before_any_chunk_finishes_errored_with_empty_content(
    repo: InMemorySessionRepository, config: ModelConfig
) -> None:
    llm = FakeLLMClient(chunks=[], error=RuntimeError("immediate"))
    session = await _make_session_with_user_message(repo, config)

    events = await _collect(
        StreamAssistantResponseHandler(sessions=repo, llm=llm),
        session.id,  # type: ignore[attr-defined]
    )

    assert [type(e).__name__ for e in events] == ["StreamStarted", "StreamFinished"]
    finished = events[-1]
    assert isinstance(finished, StreamFinished)
    assert finished.state is StreamingState.ERRORED
    assert finished.content == ""
    assert finished.message.status is MessageStatus.ERROR


# ---------------------------------------------------------------------------
# Pre-stream guards
# ---------------------------------------------------------------------------


async def test_session_not_found_raises_without_yielding_events(
    repo: InMemorySessionRepository, llm: FakeLLMClient
) -> None:
    handler = StreamAssistantResponseHandler(sessions=repo, llm=llm)
    with pytest.raises(SessionNotFound):
        await _exhaust(handler, uuid4())
    assert llm.call_count == 0


async def test_terminal_session_raises_without_yielding_events(
    repo: InMemorySessionRepository, llm: FakeLLMClient, config: ModelConfig
) -> None:
    session = await _make_session_with_user_message(repo, config)
    session.transition_to(SessionStatus.ARCHIVED)  # type: ignore[attr-defined]
    await repo.save(session)  # type: ignore[arg-type]

    handler = StreamAssistantResponseHandler(sessions=repo, llm=llm)
    with pytest.raises(SessionAlreadyTerminal):
        await _exhaust(handler, session.id)  # type: ignore[attr-defined]
    assert llm.call_count == 0


# ---------------------------------------------------------------------------
# Context-builder integration
# ---------------------------------------------------------------------------


async def test_multi_turn_context_is_passed_to_llm(
    repo: InMemorySessionRepository, llm: FakeLLMClient, config: ModelConfig
) -> None:
    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(CreateSessionCommand(user_id=uuid4(), config=config))
    # Seed a prior turn pair directly.
    session.add_user_message("first")
    session.add_assistant_message("first reply")
    await repo.save(session)
    # New user message
    await SendTextMessageHandler(sessions=repo).handle(
        SendTextMessageCommand(session_id=session.id, content="second")
    )

    handler = StreamAssistantResponseHandler(sessions=repo, llm=llm)
    await _collect(handler, session.id)

    assert llm.received_messages is not None
    assert [(m.role, m.content) for m in llm.received_messages] == [
        (MessageRole.USER, "first"),
        (MessageRole.ASSISTANT, "first reply"),
        (MessageRole.USER, "second"),
    ]


async def test_custom_context_window_is_honoured(
    repo: InMemorySessionRepository, llm: FakeLLMClient, config: ModelConfig
) -> None:
    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(CreateSessionCommand(user_id=uuid4(), config=config))
    for i in range(5):
        session.add_user_message(f"u{i}")
        session.add_assistant_message(f"a{i}")
    await repo.save(session)

    handler = StreamAssistantResponseHandler(
        sessions=repo, llm=llm, context_builder=ContextBuilder(window=2)
    )
    await _collect(handler, session.id)

    assert llm.received_messages is not None
    assert [m.content for m in llm.received_messages] == ["u4", "a4"]


async def test_session_system_prompt_is_forwarded(
    repo: InMemorySessionRepository, llm: FakeLLMClient, config: ModelConfig
) -> None:
    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(
        CreateSessionCommand(user_id=uuid4(), config=config, system_prompt="be brief")
    )
    await SendTextMessageHandler(sessions=repo).handle(
        SendTextMessageCommand(session_id=session.id, content="hi")
    )

    await _collect(StreamAssistantResponseHandler(sessions=repo, llm=llm), session.id)

    assert llm.received_system_prompt == "be brief"


# ---------------------------------------------------------------------------
# Cancellation (Phase 2.5)
# ---------------------------------------------------------------------------


async def test_cancellation_flag_set_before_first_chunk_yields_no_chunks(
    repo: InMemorySessionRepository,
    cancellations: InMemoryCancellationStore,
    llm: FakeLLMClient,
    config: ModelConfig,
) -> None:
    llm.chunks = ["a", "b", "c"]
    session = await _make_session_with_user_message(repo, config)
    await cancellations.mark_cancelled(session.id)  # type: ignore[attr-defined]

    handler = StreamAssistantResponseHandler(sessions=repo, llm=llm, cancellations=cancellations)
    events = await _collect(handler, session.id)  # type: ignore[attr-defined]

    chunks = [e for e in events if isinstance(e, StreamChunk)]
    finished = events[-1]
    assert chunks == []
    assert isinstance(finished, StreamFinished)
    assert finished.state is StreamingState.CANCELLED
    assert finished.content == ""
    assert finished.message.status is MessageStatus.CANCELLED


async def test_cancellation_after_some_chunks_preserves_partial_content(
    repo: InMemorySessionRepository,
    cancellations: InMemoryCancellationStore,
    config: ModelConfig,
) -> None:
    # The fake llm yields "hel" then "lo " then "world"; we flip the
    # cancel flag after the second chunk is emitted by calling the
    # store directly between iterations via a small adapter test.
    session = await _make_session_with_user_message(repo, config)

    # Build a custom FakeLLMClient that flips cancel after each chunk.
    class _FlippingLLM(FakeLLMClient):
        def __init__(self, *, store: InMemoryCancellationStore, sid: object) -> None:
            super().__init__(chunks=["hel", "lo ", "world"])
            self._store = store
            self._sid = sid
            self._flipped = False

        async def stream(self, **kwargs: object):  # type: ignore[no-untyped-def]
            count = 0
            async for c in super().stream(**kwargs):  # type: ignore[arg-type]
                yield c
                count += 1
                if count == 2 and not self._flipped:
                    await self._store.mark_cancelled(self._sid)  # type: ignore[arg-type]
                    self._flipped = True

    llm = _FlippingLLM(store=cancellations, sid=session.id)  # type: ignore[attr-defined]
    handler = StreamAssistantResponseHandler(sessions=repo, llm=llm, cancellations=cancellations)
    events = await _collect(handler, session.id)  # type: ignore[attr-defined]

    chunks = [e for e in events if isinstance(e, StreamChunk)]
    assert [c.text for c in chunks] == ["hel", "lo "]
    finished = events[-1]
    assert isinstance(finished, StreamFinished)
    assert finished.state is StreamingState.CANCELLED
    assert finished.content == "hel" + "lo "
    assert finished.message.status is MessageStatus.CANCELLED


async def test_clear_is_called_after_stream_completes(
    repo: InMemorySessionRepository,
    cancellations: InMemoryCancellationStore,
    llm: FakeLLMClient,
    config: ModelConfig,
) -> None:
    session = await _make_session_with_user_message(repo, config)
    handler = StreamAssistantResponseHandler(sessions=repo, llm=llm, cancellations=cancellations)
    await _collect(handler, session.id)  # type: ignore[attr-defined]

    assert cancellations.clear_calls == [session.id]  # type: ignore[attr-defined]


async def test_clear_is_called_after_stream_errors(
    repo: InMemorySessionRepository,
    cancellations: InMemoryCancellationStore,
    config: ModelConfig,
) -> None:
    llm = FakeLLMClient(chunks=[], error=RuntimeError("boom"))
    session = await _make_session_with_user_message(repo, config)
    handler = StreamAssistantResponseHandler(sessions=repo, llm=llm, cancellations=cancellations)
    await _collect(handler, session.id)  # type: ignore[attr-defined]

    assert cancellations.clear_calls == [session.id]  # type: ignore[attr-defined]


async def test_clear_is_called_after_cancellation(
    repo: InMemorySessionRepository,
    cancellations: InMemoryCancellationStore,
    llm: FakeLLMClient,
    config: ModelConfig,
) -> None:
    session = await _make_session_with_user_message(repo, config)
    await cancellations.mark_cancelled(session.id)  # type: ignore[attr-defined]

    handler = StreamAssistantResponseHandler(sessions=repo, llm=llm, cancellations=cancellations)
    await _collect(handler, session.id)  # type: ignore[attr-defined]

    assert cancellations.clear_calls == [session.id]  # type: ignore[attr-defined]
    # And the flag is no longer set.
    assert await cancellations.is_cancelled(session.id) is False  # type: ignore[attr-defined]
