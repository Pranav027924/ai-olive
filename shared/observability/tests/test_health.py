"""Tests for the health registry + router (Phase 9.3)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from olive_obs.health import HealthRegistry, build_health_router


async def _ok() -> None:
    return None


async def _boom() -> None:
    raise RuntimeError("postgres down")


def _make_client(registry: HealthRegistry) -> AsyncClient:
    app = FastAPI()
    app.include_router(build_health_router(registry))
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def passing_client() -> AsyncIterator[AsyncClient]:
    registry = HealthRegistry()
    registry.add("postgres", _ok)
    registry.add("redis", _ok)
    async with _make_client(registry) as client:
        yield client


async def test_liveness_is_always_ok() -> None:
    registry = HealthRegistry()
    registry.add("postgres", _boom)  # readiness fails…
    async with _make_client(registry) as client:
        response = await client.get("/health")
    # …but liveness only reports the process is up.
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_ok_when_all_checks_pass(passing_client: AsyncClient) -> None:
    response = await passing_client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"postgres": "ok", "redis": "ok"}}


async def test_readiness_503_when_a_check_fails() -> None:
    registry = HealthRegistry()
    registry.add("postgres", _boom)
    registry.add("redis", _ok)
    async with _make_client(registry) as client:
        response = await client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["redis"] == "ok"
    assert "postgres down" in body["checks"]["postgres"]


async def test_empty_registry_is_ready() -> None:
    async with _make_client(HealthRegistry()) as client:
        response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {}}
