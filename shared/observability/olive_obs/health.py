"""Health endpoints (PRD §9.3).

Splits liveness from readiness, matching Kubernetes probe semantics:

- ``GET /health``        liveness — always 200 while the process is up.
- ``GET /health/ready``  readiness — runs every registered dependency
                         check; 200 when all pass, 503 (with a
                         per-check breakdown) when any fail.

A check is any ``async () -> None`` that raises on failure. Services
register Postgres pings, Redis pings, etc. via :class:`HealthRegistry`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse

HealthCheck = Callable[[], Awaitable[None]]


class HealthRegistry:
    def __init__(self) -> None:
        self._checks: list[tuple[str, HealthCheck]] = []

    def add(self, name: str, check: HealthCheck) -> None:
        self._checks.append((name, check))

    async def run(self) -> tuple[bool, dict[str, str]]:
        results: dict[str, str] = {}
        healthy = True
        for name, check in self._checks:
            try:
                await check()
                results[name] = "ok"
            except Exception as exc:
                healthy = False
                results[name] = f"error: {type(exc).__name__}: {exc}"[:200]
        return healthy, results


def build_health_router(registry: HealthRegistry) -> APIRouter:
    router = APIRouter(tags=["meta"])

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/health/ready")
    async def ready() -> JSONResponse:
        healthy, checks = await registry.run()
        payload = {"status": "ok" if healthy else "degraded", "checks": checks}
        return JSONResponse(status_code=200 if healthy else 503, content=payload)

    return router
