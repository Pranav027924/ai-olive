"""HttpEmitter — batched async POST to the ingestion service (Phase 4.8).

Hot-path contract (PRD §3): ``emit`` must never block the caller.
A bounded ``asyncio.Queue`` decouples production from delivery; a
background worker drains the queue, batches up to ``max_batch`` events
or waits up to ``flush_interval_seconds``, and POSTs to the
ingestion endpoint with bounded exponential backoff on 5xx / network
errors. 4xx is a permanent failure and is not retried.

If the queue is full when ``emit`` is called the event is dropped
silently (``dropped_count`` tracks the count for metrics). Disk-spill
overflow (PRD §6.2) lands in a later phase; CompositeEmitter +
CircuitBreaker (Phase 4.9) lets the chat-service also tee to a
FileEmitter so dropped HTTP events still hit disk.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Final

import httpx
from contracts.log_event import LogEvent

from olive_sdk.application.emitter_port import EmitterPort

DEFAULT_MAX_BATCH: Final = 20
DEFAULT_FLUSH_INTERVAL_SECONDS: Final = 2.0
DEFAULT_QUEUE_SIZE: Final = 1000
DEFAULT_MAX_RETRIES: Final = 3
DEFAULT_INITIAL_BACKOFF_SECONDS: Final = 1.0
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final = 10.0


class HttpEmitter(EmitterPort):
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str = "",
        max_batch: int = DEFAULT_MAX_BATCH,
        flush_interval_seconds: float = DEFAULT_FLUSH_INTERVAL_SECONDS,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_backoff_seconds: float = DEFAULT_INITIAL_BACKOFF_SECONDS,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._max_batch = max_batch
        self._flush_interval = flush_interval_seconds
        self._max_retries = max_retries
        self._initial_backoff = initial_backoff_seconds
        self._request_timeout = request_timeout_seconds

        self._queue: asyncio.Queue[LogEvent] = asyncio.Queue(maxsize=queue_size)
        self._client: httpx.AsyncClient | None = client
        self._owned_client = client is None
        self._task: asyncio.Task[None] | None = None
        self._shutdown = asyncio.Event()
        self.dropped_count = 0
        self.delivered_count = 0
        self.failed_batches = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def emit(self, event: LogEvent) -> None:
        self._ensure_started()
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self.dropped_count += 1

    async def aclose(self) -> None:
        """Stop the worker after draining whatever is on the queue."""
        self._shutdown.set()
        if self._task is not None:
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._owned_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _ensure_started(self) -> None:
        if self._task is not None:
            return
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._request_timeout)
        self._task = asyncio.create_task(self._worker())

    async def _worker(self) -> None:
        try:
            while not self._shutdown.is_set():
                batch = await self._collect_batch()
                if batch:
                    await self._flush_with_retry(batch)
            # Final drain on shutdown so in-flight events still ship.
            remaining: list[LogEvent] = []
            while True:
                try:
                    remaining.append(self._queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            if remaining:
                await self._flush_with_retry(remaining)
        except asyncio.CancelledError:
            return

    async def _collect_batch(self) -> list[LogEvent]:
        try:
            first = await asyncio.wait_for(self._queue.get(), timeout=self._flush_interval)
        except TimeoutError:
            return []

        batch = [first]
        while len(batch) < self._max_batch:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return batch

    async def _flush_with_retry(self, batch: list[LogEvent]) -> None:
        client = self._client
        if client is None:  # pragma: no cover — _ensure_started always sets it
            return
        body = {"events": [e.model_dump(mode="json") for e in batch]}
        headers = {"x-api-key": self._api_key} if self._api_key else {}

        delay = self._initial_backoff
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await client.post(self._endpoint, json=body, headers=headers)
                if response.status_code < 400:
                    self.delivered_count += len(batch)
                    return
                if response.status_code < 500:
                    # 4xx — permanent failure, don't retry.
                    self.failed_batches += 1
                    return
                last_error = httpx.HTTPStatusError(
                    message=f"{response.status_code}",
                    request=response.request,
                    response=response,
                )
            except httpx.HTTPError as exc:
                last_error = exc

            if attempt < self._max_retries:
                await asyncio.sleep(delay)
                delay *= 2

        # All retries exhausted.
        self.failed_batches += 1
        _ = last_error  # kept for potential future logging
