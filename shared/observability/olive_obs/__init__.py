"""olive-obs — shared observability primitives for AI-OLive (PRD §9.1-9.3)."""

from __future__ import annotations

from olive_obs.fastapi_setup import install_observability
from olive_obs.health import HealthRegistry, build_health_router
from olive_obs.logging import configure_logging, get_logger
from olive_obs.metrics import PrometheusMiddleware, metrics_response
from olive_obs.request_id import REQUEST_ID_HEADER, RequestIdMiddleware

__all__ = [
    "REQUEST_ID_HEADER",
    "HealthRegistry",
    "PrometheusMiddleware",
    "RequestIdMiddleware",
    "build_health_router",
    "configure_logging",
    "get_logger",
    "install_observability",
    "metrics_response",
]
