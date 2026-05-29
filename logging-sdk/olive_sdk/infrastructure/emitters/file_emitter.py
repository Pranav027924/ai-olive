"""FileEmitter — append-only JSONL writer for LogEvents (Phase 3.8).

Used in local dev to ``tail -f logs/inference.jsonl`` while the
chat-service runs. Production uses the HTTPEmitter (Phase 4.8) and
keeps the file emitter as a tee-target via CompositeEmitter (Phase 4.9).

Design
- One JSON line per LogEvent (``model_dump_json()``), terminated by ``\n``.
- Append mode: existing content is never truncated.
- Parent directory auto-created on first emit so the SDK works with a
  fresh checkout.
- Writes are serialised by an asyncio.Lock so concurrent ``emit`` calls
  produce non-interleaved lines. The actual file I/O happens off the
  event loop via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from contracts.log_event import LogEvent

from olive_sdk.application.emitter_port import EmitterPort

DEFAULT_PATH = Path("logs") / "inference.jsonl"


class FileEmitter(EmitterPort):
    def __init__(self, *, path: Path | str | None = None) -> None:
        self._path: Path = Path(path) if path is not None else DEFAULT_PATH
        self._lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        return self._path

    async def emit(self, event: LogEvent) -> None:
        line = event.model_dump_json() + "\n"
        async with self._lock:
            await asyncio.to_thread(self._append, line)

    def _append(self, line: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)
