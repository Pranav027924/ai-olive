"""Prometheus metrics (PRD §9.2).

A pure-ASGI middleware records a request counter + latency histogram
labelled by service / method / route-template / status. Using the
route *template* (``/sessions/{session_id}``) rather than the raw
path keeps label cardinality bounded. The ``/metrics`` endpoint
exposes the default registry in the standard text format.
"""

from __future__ import annotations

import time
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests.",
    ["service", "method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["service", "method", "path"],
)


class PrometheusMiddleware:
    def __init__(self, app: Any, *, service: str) -> None:
        self.app = app
        self.service = service

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method: str = scope["method"]
        status_holder = {"code": 500}

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
            await send(message)

        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            path = _route_template(scope)
            REQUEST_COUNT.labels(self.service, method, path, str(status_holder["code"])).inc()
            REQUEST_LATENCY.labels(self.service, method, path).observe(duration)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _route_template(scope: Any) -> str:
    route = scope.get("route")
    if route is not None:
        template = getattr(route, "path_format", None) or getattr(route, "path", None)
        if template:
            return str(template)
    # No route matched (404s, raw mounts): collapse to a single label
    # so an attacker can't blow up cardinality with random URLs.
    return "unmatched"
