"""install_observability — one-call wiring for a FastAPI service (PRD §9.1-9.3).

Adds the request-id + Prometheus middlewares (request-id outermost so
the id is bound before metrics/handlers run), mounts ``/metrics``, and
includes the health router. Call it from each service's ``create_app``.
"""

from __future__ import annotations

from fastapi import FastAPI

from olive_obs.health import HealthRegistry, build_health_router
from olive_obs.metrics import PrometheusMiddleware, metrics_response
from olive_obs.request_id import RequestIdMiddleware


def install_observability(
    app: FastAPI,
    *,
    service: str,
    health: HealthRegistry | None = None,
) -> None:
    app.add_middleware(PrometheusMiddleware, service=service)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/metrics", include_in_schema=False, tags=["meta"])
    async def metrics() -> object:
        return metrics_response()

    app.include_router(build_health_router(health or HealthRegistry()))
