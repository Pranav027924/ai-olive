"""Dashboard service FastAPI app (PRD §7.11, obs in 9.1-9.3)."""

from __future__ import annotations

from fastapi import FastAPI
from olive_obs import HealthRegistry, configure_logging, install_observability

from dashboard_service.interfaces.http.dependencies import clickhouse_health_check
from dashboard_service.interfaces.http.routers import metrics


def create_app() -> FastAPI:
    configure_logging(service="dashboard-service")
    app = FastAPI(
        title="AI-OLive Dashboard Service",
        version="0.1.0",
        description="Read-only analytics over inference_metrics (PRD §7).",
    )

    health = HealthRegistry()
    health.add("clickhouse", clickhouse_health_check)
    install_observability(app, service="dashboard-service", health=health)

    app.include_router(metrics.router)
    return app


app: FastAPI = create_app()
