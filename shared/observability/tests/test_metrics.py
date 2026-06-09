"""Tests for the Prometheus middleware + endpoint (Phase 9.2)."""

from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from olive_obs.metrics import PrometheusMiddleware, metrics_response


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(PrometheusMiddleware, service="test-svc")

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> object:
        return metrics_response()

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    return app


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test")


async def test_metrics_endpoint_exposes_request_counter() -> None:
    async with _client() as client:
        await client.get("/items/abc")
        await client.get("/items/def")
        body = (await client.get("/metrics")).text
    assert "http_requests_total" in body
    assert 'service="test-svc"' in body


async def test_route_template_collapses_path_params() -> None:
    """Two requests to /items/{id} with different ids must share one
    metric series keyed by the template, not the literal path."""
    async with _client() as client:
        await client.get("/items/abc")
        await client.get("/items/def")
        body = (await client.get("/metrics")).text
    assert 'path="/items/{item_id}"' in body
    assert 'path="/items/abc"' not in body


async def test_unmatched_paths_collapse_to_single_label() -> None:
    async with _client() as client:
        await client.get("/this/does/not/exist")
        body = (await client.get("/metrics")).text
    assert 'path="unmatched"' in body


async def test_latency_histogram_present() -> None:
    async with _client() as client:
        await client.get("/items/x")
        body = (await client.get("/metrics")).text
    assert "http_request_duration_seconds" in body
