"""olive-obs — shared observability primitives for AI-OLive (PRD §9.1-9.3).

``configure_logging`` / ``get_logger`` and the pure-ASGI middlewares only
need structlog/starlette/prometheus, so they're imported eagerly. The
FastAPI-dependent helpers (``install_observability``, ``HealthRegistry``,
``build_health_router``) are loaded lazily via :pep:`562` ``__getattr__``
so non-web consumers — notably the worker CLI — can ``import olive_obs``
without FastAPI installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from olive_obs.logging import configure_logging, get_logger
from olive_obs.metrics import PrometheusMiddleware, metrics_response
from olive_obs.request_id import REQUEST_ID_HEADER, RequestIdMiddleware

if TYPE_CHECKING:
    from olive_obs.fastapi_setup import install_observability as install_observability
    from olive_obs.health import HealthRegistry as HealthRegistry
    from olive_obs.health import build_health_router as build_health_router

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


def __getattr__(name: str) -> Any:
    if name == "install_observability":
        from olive_obs.fastapi_setup import install_observability

        return install_observability
    if name in ("HealthRegistry", "build_health_router"):
        from olive_obs import health

        return getattr(health, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
