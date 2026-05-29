"""Tests for FileEmitter (Phase 3.8)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from contracts.log_event import LogEvent
from olive_sdk.infrastructure.emitters.file_emitter import FileEmitter


def _event(**overrides: object) -> LogEvent:
    base: dict[str, object] = {
        "event_id": uuid4(),
        "session_id": uuid4(),
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "status": "success",
        "started_at": datetime(2026, 1, 1, tzinfo=UTC),
        "finished_at": datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        "latency_ms": 1000,
        "input_preview": "hi",
        "output_preview": "hello",
        "sdk_version": "0.1.0",
    }
    base.update(overrides)
    return LogEvent(**base)  # type: ignore[arg-type]


@pytest.fixture
def jsonl_path(tmp_path: Path) -> Path:
    return tmp_path / "inference.jsonl"


async def test_emit_one_event_produces_one_jsonl_line(jsonl_path: Path) -> None:
    emitter = FileEmitter(path=jsonl_path)
    ev = _event()

    await emitter.emit(ev)

    content = jsonl_path.read_text()
    assert content.endswith("\n")
    lines = [ln for ln in content.splitlines() if ln]
    assert len(lines) == 1
    decoded = json.loads(lines[0])
    assert decoded["event_id"] == str(ev.event_id)
    assert decoded["status"] == "success"


async def test_multiple_events_become_multiple_lines_in_order(jsonl_path: Path) -> None:
    emitter = FileEmitter(path=jsonl_path)
    events = [_event(input_preview=f"hi-{i}", session_id=uuid4()) for i in range(5)]

    for ev in events:
        await emitter.emit(ev)

    lines = jsonl_path.read_text().splitlines()
    assert len(lines) == 5
    decoded = [json.loads(ln) for ln in lines]
    assert [d["input_preview"] for d in decoded] == ["hi-0", "hi-1", "hi-2", "hi-3", "hi-4"]


async def test_concurrent_emits_do_not_interleave(jsonl_path: Path) -> None:
    emitter = FileEmitter(path=jsonl_path)
    events = [_event(input_preview=f"e-{i}") for i in range(20)]

    await asyncio.gather(*(emitter.emit(e) for e in events))

    lines = jsonl_path.read_text().splitlines()
    assert len(lines) == 20
    # Each line is valid JSON (no torn writes).
    parsed = [json.loads(ln) for ln in lines]
    assert {p["input_preview"] for p in parsed} == {f"e-{i}" for i in range(20)}


async def test_appends_to_existing_file_without_truncating(jsonl_path: Path) -> None:
    jsonl_path.write_text('{"pre-existing": true}\n', encoding="utf-8")
    emitter = FileEmitter(path=jsonl_path)

    await emitter.emit(_event())

    lines = jsonl_path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"pre-existing": True}


async def test_creates_parent_directory_if_missing(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nested" / "inference.jsonl"
    emitter = FileEmitter(path=nested)

    await emitter.emit(_event())

    assert nested.exists()


async def test_round_trips_event_through_json(jsonl_path: Path) -> None:
    emitter = FileEmitter(path=jsonl_path)
    original = _event(prompt_tokens=10, completion_tokens=20)

    await emitter.emit(original)

    line = jsonl_path.read_text().splitlines()[0]
    restored = LogEvent.model_validate_json(line)
    assert restored == original


def test_default_path_is_logs_inference_jsonl() -> None:
    emitter = FileEmitter()
    assert emitter.path == Path("logs") / "inference.jsonl"
