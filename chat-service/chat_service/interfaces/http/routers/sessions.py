"""Sessions router — create, list, get."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from chat_service.application.use_cases.create_session import CreateSessionCommand
from chat_service.application.use_cases.list_sessions import ListSessionsQuery
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.session_status import SessionStatus
from chat_service.interfaces.http.dependencies import (
    CreateSessionDep,
    CurrentUserDep,
    ListSessionsDep,
    RepoDep,
)
from chat_service.interfaces.http.schemas import (
    CreateSessionRequest,
    SessionView,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionView, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionRequest,
    handler: CreateSessionDep,
    user_id: CurrentUserDep,
) -> SessionView:
    session = await handler.handle(
        CreateSessionCommand(
            user_id=user_id,
            config=ModelConfig(provider=body.provider, model=body.model),
            title=body.title,
            system_prompt=body.system_prompt,
        )
    )
    return SessionView.from_domain(session)


@router.get("", response_model=list[SessionView])
async def list_sessions(
    handler: ListSessionsDep,
    user_id: CurrentUserDep,
    status_filter: Annotated[SessionStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SessionView]:
    rows = await handler.handle(
        ListSessionsQuery(
            user_id=user_id,
            status=status_filter,
            limit=limit,
            offset=offset,
        )
    )
    return [SessionView.from_domain(s) for s in rows]


@router.get("/{session_id}", response_model=SessionView)
async def get_session(session_id: UUID, repo: RepoDep) -> SessionView:
    session = await repo.get(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    return SessionView.from_domain(session)
