"""FastAPI application factory.

Building the app via a factory makes it easy for tests to override
dependencies and for the entry point in :mod:`main` to start uvicorn.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from chat_service.domain.errors import (
    InvalidStatusTransition,
    SessionAlreadyTerminal,
    SessionNotFound,
)
from chat_service.interfaces.http.routers import messages, sessions, stream


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI-OLive Chat Service",
        version="0.1.0",
        description="PRD §6.1. Sessions + messages. Streaming arrives in Phase 2.",
    )

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    _register_domain_exception_handlers(app)

    app.include_router(sessions.router)
    app.include_router(messages.router)
    app.include_router(stream.router)

    return app


def _register_domain_exception_handlers(app: FastAPI) -> None:
    """Map domain exceptions to RFC 7807 problem details (PRD §9.6)."""

    def _problem(status_code: int, title: str, detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={
                "type": "about:blank",
                "title": title,
                "status": status_code,
                "detail": detail,
            },
            media_type="application/problem+json",
        )

    @app.exception_handler(SessionNotFound)
    async def _session_not_found(_: Request, exc: SessionNotFound) -> JSONResponse:
        return _problem(404, "session not found", str(exc))

    @app.exception_handler(SessionAlreadyTerminal)
    async def _session_terminal(_: Request, exc: SessionAlreadyTerminal) -> JSONResponse:
        return _problem(409, "session already terminal", str(exc))

    @app.exception_handler(InvalidStatusTransition)
    async def _invalid_transition(_: Request, exc: InvalidStatusTransition) -> JSONResponse:
        return _problem(409, "invalid status transition", str(exc))


# Convenience module-level app for `uvicorn chat_service.interfaces.http.app:app`.
app: FastAPI = create_app()
