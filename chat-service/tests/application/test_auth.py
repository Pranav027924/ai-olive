"""Tests for register/authenticate use cases (Phase 9.4 login)."""

from __future__ import annotations

from uuid import UUID

import pytest
from chat_service.application.ports.user_repository import UserRepository
from chat_service.application.use_cases.authenticate_user import (
    AuthenticateUserCommand,
    AuthenticateUserHandler,
)
from chat_service.application.use_cases.register_user import (
    RegisterUserCommand,
    RegisterUserHandler,
)
from chat_service.domain.entities.user import User
from chat_service.domain.errors import EmailAlreadyRegistered, InvalidCredentials
from chat_service.infrastructure.auth.password_hasher import BcryptPasswordHasher


class _InMemoryUsers(UserRepository):
    def __init__(self) -> None:
        self._by_email: dict[str, User] = {}
        self._by_id: dict[UUID, User] = {}

    async def get_by_email(self, email: str) -> User | None:
        return self._by_email.get(email)

    async def get(self, user_id: UUID) -> User | None:
        return self._by_id.get(user_id)

    async def create(self, user: User) -> None:
        self._by_email[user.email] = user
        self._by_id[user.id] = user


def _handlers() -> tuple[_InMemoryUsers, RegisterUserHandler, AuthenticateUserHandler]:
    users = _InMemoryUsers()
    hasher = BcryptPasswordHasher()
    return (
        users,
        RegisterUserHandler(users=users, hasher=hasher),
        AuthenticateUserHandler(users=users, hasher=hasher),
    )


async def test_register_creates_a_hashed_user() -> None:
    users, register, _ = _handlers()
    user = await register.handle(RegisterUserCommand(email="A@Example.com ", password="hunter2pass"))
    assert user.email == "a@example.com"  # normalised
    assert user.password_hash and user.password_hash != "hunter2pass"  # hashed, not plaintext
    assert await users.get_by_email("a@example.com") is not None


async def test_register_rejects_duplicate_email() -> None:
    _, register, _ = _handlers()
    await register.handle(RegisterUserCommand(email="dup@example.com", password="hunter2pass"))
    with pytest.raises(EmailAlreadyRegistered):
        await register.handle(RegisterUserCommand(email="dup@example.com", password="another1pass"))


async def test_login_succeeds_with_correct_password() -> None:
    _, register, login = _handlers()
    created = await register.handle(
        RegisterUserCommand(email="me@example.com", password="correct-horse")
    )
    authed = await login.handle(AuthenticateUserCommand(email="me@example.com", password="correct-horse"))
    assert authed.id == created.id


async def test_login_fails_with_wrong_password() -> None:
    _, register, login = _handlers()
    await register.handle(RegisterUserCommand(email="me@example.com", password="correct-horse"))
    with pytest.raises(InvalidCredentials):
        await login.handle(AuthenticateUserCommand(email="me@example.com", password="wrong-pass"))


async def test_login_fails_for_unknown_email() -> None:
    _, _, login = _handlers()
    with pytest.raises(InvalidCredentials):
        await login.handle(AuthenticateUserCommand(email="nobody@example.com", password="whatever1"))


def test_password_hasher_roundtrip_and_rejects_wrong() -> None:
    h = BcryptPasswordHasher()
    digest = h.hash("s3cret-password")
    assert h.verify("s3cret-password", digest) is True
    assert h.verify("not-it", digest) is False
