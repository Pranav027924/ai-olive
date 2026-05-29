"""Alembic environment for worker-service.

Same async-engine pattern as chat-service; the version table lives
in ``public`` so the first migration can ``CREATE SCHEMA logs``.

Run from inside ``worker-service/``:

    uv run alembic upgrade head
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from worker_service.config import WorkerSettings
from worker_service.infrastructure.persistence.sqlalchemy_models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = WorkerSettings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    """Only consider objects under the logs schema."""
    return not (type_ == "table" and getattr(obj, "schema", None) != "logs")


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        include_schemas=True,
        include_object=_include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="alembic_version_worker",
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_object=_include_object,
        version_table="alembic_version_worker",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
