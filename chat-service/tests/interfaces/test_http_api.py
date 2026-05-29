"""HTTP tests for the chat-service FastAPI app (Phase 1.10).

Dependency overrides swap the real Postgres repo and Anthropic LLM
client for the in-memory fakes from ``tests/conftest.py`` so these
tests stay unit-fast.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from chat_service.application.ports.llm_client import LLMClient
from chat_service.application.ports.session_repository import SessionRepository
from chat_service.domain.entities.session import Session
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.session_status import SessionStatus
from chat_service.interfaces.http.app import create_app
from chat_service.interfaces.http.dependencies import (
    get_dev_user_id,
    get_llm,
    get_repository,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.conftest import FakeLLMClient, InMemorySessionRepository

DEV_USER = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def http_repo() -> InMemorySessionRepository:
    return InMemorySessionRepository()


@pytest.fixture
def http_llm() -> FakeLLMClient:
    return FakeLLMClient(response="hi back")


@pytest.fixture
def app(http_repo: InMemorySessionRepository, http_llm: FakeLLMClient) -> FastAPI:
    app = create_app()

    def _repo() -> SessionRepository:
        return http_repo

    def _llm() -> LLMClient:
        return http_llm

    def _user() -> UUID:
        return DEV_USER

    app.dependency_overrides[get_repository] = _repo
    app.dependency_overrides[get_llm] = _llm
    app.dependency_overrides[get_dev_user_id] = _user
    return app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


async def test_health(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /sessions
# ---------------------------------------------------------------------------


async def test_create_session_returns_201_and_persists(
    client: AsyncClient, http_repo: InMemorySessionRepository
) -> None:
    r = await client.post(
        "/sessions",
        json={"title": "hi", "system_prompt": "be brief"},
    )

    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "hi"
    assert body["system_prompt"] == "be brief"
    assert body["status"] == "active"
    assert body["provider"] == "anthropic"
    assert body["model"] == "claude-opus-4-7"
    assert body["messages"] == []
    assert UUID(body["id"])
    assert UUID(body["user_id"]) == DEV_USER

    persisted = await http_repo.get(UUID(body["id"]))
    assert persisted is not None


async def test_create_session_with_minimal_body(client: AsyncClient) -> None:
    r = await client.post("/sessions", json={})
    assert r.status_code == 201
    body = r.json()
    assert body["title"] is None
    assert body["system_prompt"] is None


async def test_create_session_rejects_unknown_provider(client: AsyncClient) -> None:
    r = await client.post("/sessions", json={"provider": "cohere"})
    assert r.status_code == 422


async def test_create_session_rejects_extra_fields(client: AsyncClient) -> None:
    r = await client.post("/sessions", json={"extra": "nope"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /sessions
# ---------------------------------------------------------------------------


async def test_list_sessions_empty(client: AsyncClient) -> None:
    r = await client.get("/sessions")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_sessions_returns_user_rows(
    client: AsyncClient, http_repo: InMemorySessionRepository
) -> None:
    cfg = ModelConfig(provider="anthropic", model="claude-opus-4-7")
    for title in ("a", "b", "c"):
        http_repo.seed([Session.create(user_id=DEV_USER, config=cfg, title=title)])

    r = await client.get("/sessions")
    assert r.status_code == 200
    titles = sorted(s["title"] for s in r.json())
    assert titles == ["a", "b", "c"]


async def test_list_sessions_status_filter(
    client: AsyncClient, http_repo: InMemorySessionRepository
) -> None:
    cfg = ModelConfig(provider="anthropic", model="claude-opus-4-7")
    active = Session.create(user_id=DEV_USER, config=cfg, title="active")
    done = Session.create(user_id=DEV_USER, config=cfg, title="done")
    done.transition_to(SessionStatus.COMPLETED)
    http_repo.seed([active, done])

    r = await client.get("/sessions", params={"status": "completed"})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["title"] == "done"


async def test_list_sessions_pagination(
    client: AsyncClient, http_repo: InMemorySessionRepository
) -> None:
    cfg = ModelConfig(provider="anthropic", model="claude-opus-4-7")
    http_repo.seed([Session.create(user_id=DEV_USER, config=cfg, title=f"s{i}") for i in range(5)])

    r = await client.get("/sessions", params={"limit": 2, "offset": 0})
    assert r.status_code == 200
    assert len(r.json()) == 2


# ---------------------------------------------------------------------------
# GET /sessions/{id}
# ---------------------------------------------------------------------------


async def test_get_session_by_id(client: AsyncClient) -> None:
    created = await client.post("/sessions", json={"title": "hello"})
    sid = created.json()["id"]

    r = await client.get(f"/sessions/{sid}")
    assert r.status_code == 200
    assert r.json()["id"] == sid


async def test_get_session_unknown_id_returns_404_problem_json(client: AsyncClient) -> None:
    r = await client.get(f"/sessions/{uuid4()}")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /chat/{id}/messages
# ---------------------------------------------------------------------------


async def test_send_message_happy_path_returns_user_message(client: AsyncClient) -> None:
    created = await client.post("/sessions", json={"system_prompt": "be brief"})
    sid = created.json()["id"]

    r = await client.post(f"/chat/{sid}/messages", json={"content": "hi"})

    assert r.status_code == 201
    body = r.json()
    assert body["content"] == "hi"
    assert body["role"] == "user"
    assert body["seq"] == 1
    assert body["status"] == "complete"


async def test_send_message_does_not_invoke_llm(
    client: AsyncClient, http_llm: FakeLLMClient
) -> None:
    created = await client.post("/sessions", json={})
    sid = created.json()["id"]
    await client.post(f"/chat/{sid}/messages", json={"content": "hi"})
    # POST /messages is user-only in Phase 2; the assistant reply moves to GET /stream.
    assert http_llm.call_count == 0


async def test_send_message_unknown_session_returns_404_problem_json(
    client: AsyncClient,
) -> None:
    r = await client.post(f"/chat/{uuid4()}/messages", json={"content": "hi"})
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 404
    assert body["title"] == "session not found"


async def test_send_message_empty_content_is_422(client: AsyncClient) -> None:
    created = await client.post("/sessions", json={})
    sid = created.json()["id"]
    r = await client.post(f"/chat/{sid}/messages", json={"content": ""})
    assert r.status_code == 422


async def test_send_message_on_terminal_session_returns_409_problem_json(
    client: AsyncClient, http_repo: InMemorySessionRepository
) -> None:
    cfg = ModelConfig(provider="anthropic", model="claude-opus-4-7")
    s = Session.create(user_id=DEV_USER, config=cfg)
    s.transition_to(SessionStatus.ARCHIVED)
    http_repo.seed([s])

    r = await client.post(f"/chat/{s.id}/messages", json={"content": "hi"})
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["title"] == "session already terminal"
