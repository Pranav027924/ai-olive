"""Auth wiring tests for get_current_user_id (Phase 9.4)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import jwt
import pytest
import pytest_asyncio
from chat_service.config import ChatServiceSettings
from chat_service.interfaces.http.app import create_app
from chat_service.interfaces.http.dependencies import get_current_user_id, get_settings
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

SECRET = "interface-test-secret-at-least-32-bytes-long"


def _auth_settings() -> ChatServiceSettings:
    return ChatServiceSettings(disable_auth=False, jwt_secret=SECRET, jwt_algorithm="HS256")


def _bearer(user_id: str) -> dict[str, str]:
    token = jwt.encode({"sub": user_id}, SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Direct dependency-function behaviour
# ---------------------------------------------------------------------------


def test_disabled_auth_returns_dev_user() -> None:
    settings = ChatServiceSettings(disable_auth=True)
    assert get_current_user_id(settings, None) == settings.dev_user_id


def test_enabled_auth_missing_header_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        get_current_user_id(_auth_settings(), None)
    assert exc.value.status_code == 401


def test_enabled_auth_valid_token_returns_user_id() -> None:
    user_id = uuid4()
    token = jwt.encode({"sub": str(user_id)}, SECRET, algorithm="HS256")
    assert get_current_user_id(_auth_settings(), f"Bearer {token}") == user_id


def test_enabled_auth_bad_token_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        get_current_user_id(_auth_settings(), "Bearer not-a-jwt")
    assert exc.value.status_code == 401


def test_enabled_auth_non_bearer_scheme_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        get_current_user_id(_auth_settings(), "Basic abc123")
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# Full app: the dependency is actually attached to protected routes
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_client() -> AsyncIterator[AsyncClient]:
    app: FastAPI = create_app()
    app.dependency_overrides[get_settings] = _auth_settings
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_protected_route_401_without_token(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/sessions")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_protected_route_401_with_garbage_token(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/sessions", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401


async def test_health_is_not_protected(auth_client: AsyncClient) -> None:
    # Liveness must never require a token, or k8s probes would fail.
    response = await auth_client.get("/health")
    assert response.status_code == 200
