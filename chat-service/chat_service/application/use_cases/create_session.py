"""CreateSession — command use case."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from chat_service.application.ports.session_repository import SessionRepository
from chat_service.domain.entities.session import Session
from chat_service.domain.value_objects.model_config import ModelConfig


@dataclass(frozen=True, slots=True)
class CreateSessionCommand:
    user_id: UUID
    config: ModelConfig
    title: str | None = None
    system_prompt: str | None = None


class CreateSessionHandler:
    def __init__(self, *, sessions: SessionRepository) -> None:
        self._sessions = sessions

    async def handle(self, cmd: CreateSessionCommand) -> Session:
        session = Session.create(
            user_id=cmd.user_id,
            config=cmd.config,
            title=cmd.title,
            system_prompt=cmd.system_prompt,
        )
        await self._sessions.save(session)
        return session
