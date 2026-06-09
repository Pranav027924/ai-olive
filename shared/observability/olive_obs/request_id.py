"""RequestIdMiddleware — pure-ASGI request correlation (PRD §9.1).

Implemented as a raw ASGI middleware rather than Starlette's
``BaseHTTPMiddleware`` on purpose: BaseHTTPMiddleware buffers the
response body, which would break the chat-service SSE stream. The
raw form passes ``send`` straight through, only peeking at the
``http.response.start`` message to stamp the header.

Each request gets an ``X-Request-ID`` (echoed from the client if
present, otherwise generated). The id is bound into structlog's
contextvars so every log line emitted while handling the request
carries it, and is cleared afterwards so ids never leak between
requests sharing an event-loop task.
"""

from __future__ import annotations

import uuid
from typing import Any

from starlette.datastructures import MutableHeaders
from structlog.contextvars import bind_contextvars, clear_contextvars

REQUEST_ID_HEADER = "x-request-id"


class RequestIdMiddleware:
    def __init__(self, app: Any, *, header_name: str = REQUEST_ID_HEADER) -> None:
        self.app = app
        self.header_name = header_name.lower()

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_id(scope, self.header_name) or uuid.uuid4().hex
        clear_contextvars()
        bind_contextvars(request_id=request_id)

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers[self.header_name] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            clear_contextvars()


def _incoming_id(scope: Any, header_name: str) -> str | None:
    target = header_name.encode()
    for key, value in scope.get("headers", []):
        if key == target and value:
            decoded: str = value.decode("latin-1")
            return decoded
    return None
