"""Dashboard service FastAPI app (PRD §7.11)."""

from __future__ import annotations

from fastapi import FastAPI

from dashboard_service.interfaces.http.routers import metrics


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI-OLive Dashboard Service",
        version="0.1.0",
        description="Read-only analytics over inference_metrics (PRD §7).",
    )

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(metrics.router)
    return app


app: FastAPI = create_app()
