"""Locust load test for the Chat service (PRD §9.7).

Each simulated user creates a session once, then repeatedly posts a
message and drains the SSE reply stream — the realistic chat hot path
(session lookup, context build, LLM stream, persistence).

Run (chat on :8000)::

    uvx --from locust locust -f load/locustfile_chat.py \
        --host http://127.0.0.1:8000 \
        --users 20 --spawn-rate 5 --run-time 2m

Env:
    CHAT_BEARER_TOKEN   optional JWT; sent as Authorization: Bearer …
                        when DISABLE_AUTH=false on the server.
    CHAT_PROVIDER       provider for new sessions (default anthropic)
    CHAT_MODEL          model for new sessions (default claude-opus-4-7)

Note: with a real provider key set this drives live LLM calls and
incurs cost. Point it at a stub/mock model for pure throughput tests.
"""

from __future__ import annotations

import os

from locust import HttpUser, between, task

TOKEN = os.getenv("CHAT_BEARER_TOKEN", "")
PROVIDER = os.getenv("CHAT_PROVIDER", "anthropic")
MODEL = os.getenv("CHAT_MODEL", "claude-opus-4-7")


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


class ChatUser(HttpUser):
    wait_time = between(1.0, 3.0)

    def on_start(self) -> None:
        response = self.client.post(
            "/sessions",
            json={"title": "loadtest", "provider": PROVIDER, "model": MODEL},
            headers=_headers(),
            name="POST /sessions",
        )
        self.session_id = response.json()["id"] if response.ok else None

    @task(3)
    def send_and_stream(self) -> None:
        if not self.session_id:
            return
        self.client.post(
            f"/chat/{self.session_id}/messages",
            json={"content": "Say hello in one short sentence."},
            headers=_headers(),
            name="POST /chat/{id}/messages",
        )
        with self.client.get(
            f"/chat/{self.session_id}/stream",
            headers={**_headers(), "Accept": "text/event-stream"},
            name="GET /chat/{id}/stream",
            stream=True,
            catch_response=True,
        ) as response:
            # Drain the stream so the server-side generator runs to
            # completion; we don't parse events, just measure throughput.
            for _ in response.iter_lines():
                pass
            response.success()

    @task(1)
    def list_sessions(self) -> None:
        self.client.get("/sessions", headers=_headers(), name="GET /sessions")
