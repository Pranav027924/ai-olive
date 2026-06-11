"""AuthenticateUser — verify credentials (PRD §9.4)."""

from __future__ import annotations

from dataclasses import dataclass

from chat_service.application.ports.user_repository import UserRepository
from chat_service.application.use_cases.register_user import PasswordHasher
from chat_service.domain.entities.user import User
from chat_service.domain.errors import InvalidCredentials


@dataclass(frozen=True, slots=True)
class AuthenticateUserCommand:
    email: str
    password: str


class AuthenticateUserHandler:
    def __init__(self, *, users: UserRepository, hasher: PasswordHasher) -> None:
        self._users = users
        self._hasher = hasher

    async def handle(self, cmd: AuthenticateUserCommand) -> User:
        user = await self._users.get_by_email(cmd.email.strip().lower())
        if user is None or not user.password_hash:
            raise InvalidCredentials("invalid email or password")
        if not self._hasher.verify(cmd.password, user.password_hash):
            raise InvalidCredentials("invalid email or password")
        return user
