"""RegisterUser — create an account (PRD §9.4)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from chat_service.application.ports.user_repository import UserRepository
from chat_service.domain.entities.user import User
from chat_service.domain.errors import EmailAlreadyRegistered


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password: str, password_hash: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class RegisterUserCommand:
    email: str
    password: str


class RegisterUserHandler:
    def __init__(
        self,
        *,
        users: UserRepository,
        hasher: PasswordHasher,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._clock = clock
        self._id_factory = id_factory

    async def handle(self, cmd: RegisterUserCommand) -> User:
        email = cmd.email.strip().lower()
        if await self._users.get_by_email(email) is not None:
            raise EmailAlreadyRegistered(email)
        user = User(
            id=self._id_factory(),
            email=email,
            password_hash=self._hasher.hash(cmd.password),
            created_at=self._clock(),
        )
        await self._users.create(user)
        return user
