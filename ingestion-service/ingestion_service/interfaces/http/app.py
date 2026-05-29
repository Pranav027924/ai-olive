"""FastAPI app factory for the ingestion service (Phase 4.6)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ingestion_service.domain.errors import BatchTooLarge, EmptyBatch
from ingestion_service.interfaces.http.routers import logs


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI-OLive Ingestion Service",
        version="0.1.0",
        description="PRD §6.3. POST /v1/logs → Redis Streams.",
    )

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    _register_domain_exception_handlers(app)
    app.include_router(logs.router)
    return app


def _register_domain_exception_handlers(app: FastAPI) -> None:
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

    @app.exception_handler(EmptyBatch)
    async def _empty_batch(_: Request, exc: EmptyBatch) -> JSONResponse:
        return _problem(400, "empty batch", "events list must not be empty")

    @app.exception_handler(BatchTooLarge)
    async def _batch_too_large(_: Request, exc: BatchTooLarge) -> JSONResponse:
        return _problem(
            400,
            "batch too large",
            f"batch of {exc.size} exceeds the {exc.limit} cap",
        )


app: FastAPI = create_app()
