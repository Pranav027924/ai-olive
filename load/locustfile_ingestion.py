"""Locust load test for the Ingestion service (PRD §9.7).

Hammers ``POST /v1/logs`` with batches of valid LogEvents, exercising
the auth check + Redis XADD hot path.

Run (ingestion on :8001)::

    uvx --from locust locust -f load/locustfile_ingestion.py \
        --host http://127.0.0.1:8001 \
        --users 50 --spawn-rate 10 --run-time 2m

Env:
    INGESTION_API_KEY   x-api-key sent on every request (default
                        local-dev-ingestion-key)
    LOG_BATCH_SIZE      events per POST (default 10)
"""

from __future__ import annotations

import os
import random
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from locust import HttpUser, between, task

API_KEY = os.getenv("INGESTION_API_KEY", "local-dev-ingestion-key")
BATCH_SIZE = int(os.getenv("LOG_BATCH_SIZE", "10"))
PROVIDERS = ["anthropic", "openai", "gemini", "deepseek"]
STATUSES = ["success", "success", "success", "error"]  # ~25% errors


def _event() -> dict[str, object]:
    started = datetime.now(tz=UTC)
    latency = random.randint(50, 4000)
    status = random.choice(STATUSES)
    return {
        "event_id": str(uuid4()),
        "session_id": str(uuid4()),
        "message_id": str(uuid4()),
        "provider": random.choice(PROVIDERS),
        "model": "load-test-model",
        "status": status,
        "started_at": started.isoformat(),
        "finished_at": (started + timedelta(milliseconds=latency)).isoformat(),
        "latency_ms": latency,
        "ttft_ms": random.randint(10, 400),
        "prompt_tokens": random.randint(10, 2000),
        "completion_tokens": random.randint(10, 2000),
        "input_preview": "load test input",
        "output_preview": "load test output",
        "error_type": "RateLimitError" if status == "error" else None,
        "error_message": "429" if status == "error" else None,
        "http_status": 429 if status == "error" else 200,
        "raw_metadata": {"source": "locust"},
        "sdk_version": "loadtest-0.1.0",
    }


class IngestionUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task
    def post_logs(self) -> None:
        body = {"events": [_event() for _ in range(BATCH_SIZE)]}
        self.client.post(
            "/v1/logs",
            json=body,
            headers={"x-api-key": API_KEY},
            name="POST /v1/logs",
        )
