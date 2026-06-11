"""PostgresSessionRepository — adapter for :class:`SessionRepository`.

Maps :class:`chat_service.domain.entities.session.Session` aggregates
to the ORM rows in :mod:`sqlalchemy_models` and back again.

Persistence model (Phase 1):
- ``save`` upserts the session row and appends any new messages
  (messages are immutable for the moment; Phase 2 will start updating
  message status during streaming).
- ``get`` and ``list_for_user`` eagerly load messages so the caller
  always sees the full aggregate.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from chat_service.application.ports.session_repository import SessionRepository
from chat_service.domain.entities.message import Message
from chat_service.domain.entities.session import Session
from chat_service.domain.value_objects.message_role import MessageRole
from chat_service.domain.value_objects.message_status import MessageStatus
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.session_status import SessionStatus

from .sqlalchemy_models import MessageRow, SessionRow


class PostgresSessionRepository(SessionRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get(self, session_id: UUID) -> Session | None:
        async with self._sessionmaker() as db:
            row = await db.scalar(
                select(SessionRow)
                .where(SessionRow.id == session_id)
                .options(selectinload(SessionRow.messages))
            )
            if row is None:
                return None
            return _row_to_domain(row)

    async def save(self, session: Session) -> None:
        async with self._sessionmaker() as db, db.begin():
            row = await db.scalar(
                select(SessionRow)
                .where(SessionRow.id == session.id)
                .options(selectinload(SessionRow.messages))
            )
            if row is None:
                row = SessionRow(
                    id=session.id,
                    user_id=session.user_id,
                    title=session.title,
                    system_prompt=session.system_prompt,
                    provider=session.config.provider,
                    model=session.config.model,
                    status=session.status.value,
                    created_at=session.created_at,
                    updated_at=session.updated_at,
                )
                db.add(row)
            else:
                row.title = session.title
                row.system_prompt = session.system_prompt
                row.provider = session.config.provider
                row.model = session.config.model
                row.status = session.status.value
                row.updated_at = session.updated_at

            persisted_ids = {m.id for m in row.messages}
            for msg in session.messages:
                if msg.id in persisted_ids:
                    continue
                row.messages.append(
                    MessageRow(
                        id=msg.id,
                        session_id=session.id,
                        role=msg.role.value,
                        content=msg.content,
                        seq=msg.seq,
                        status=msg.status.value,
                        created_at=msg.created_at,
                    )
                )

    async def delete(self, session_id: UUID) -> None:
        async with self._sessionmaker() as db, db.begin():
            row = await db.scalar(select(SessionRow).where(SessionRow.id == session_id))
            if row is not None:
                await db.delete(row)

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        status: SessionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Session]:
        async with self._sessionmaker() as db:
            stmt = (
                select(SessionRow)
                .where(SessionRow.user_id == user_id)
                .options(selectinload(SessionRow.messages))
                .order_by(SessionRow.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            if status is not None:
                stmt = stmt.where(SessionRow.status == status.value)
            rows = (await db.scalars(stmt)).all()
            return [_row_to_domain(r) for r in rows]


def _row_to_domain(row: SessionRow) -> Session:
    return Session(
        id=row.id,
        user_id=row.user_id,
        title=row.title,
        system_prompt=row.system_prompt,
        config=ModelConfig(provider=row.provider, model=row.model),
        status=SessionStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        messages=[
            Message(
                id=m.id,
                role=MessageRole(m.role),
                content=m.content,
                seq=m.seq,
                status=MessageStatus(m.status),
                created_at=m.created_at,
            )
            for m in row.messages
        ],
    )
