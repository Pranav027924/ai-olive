"""PostgresUserRepository — :class:`UserRepository` adapter (PRD §9.4)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chat_service.application.ports.user_repository import UserRepository
from chat_service.domain.entities.user import User

from .sqlalchemy_models import UserRow


class PostgresUserRepository(UserRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_by_email(self, email: str) -> User | None:
        async with self._sessionmaker() as db:
            row = await db.scalar(select(UserRow).where(UserRow.email == email))
            return _to_domain(row) if row else None

    async def get(self, user_id: UUID) -> User | None:
        async with self._sessionmaker() as db:
            row = await db.scalar(select(UserRow).where(UserRow.id == user_id))
            return _to_domain(row) if row else None

    async def create(self, user: User) -> None:
        async with self._sessionmaker() as db, db.begin():
            db.add(
                UserRow(
                    id=user.id,
                    email=user.email,
                    password_hash=user.password_hash,
                    created_at=user.created_at,
                )
            )


def _to_domain(row: UserRow) -> User:
    return User(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        created_at=row.created_at,
    )
