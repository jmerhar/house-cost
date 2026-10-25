"""Alembic environment.

Runs migrations through the application's own engine and settings, so `alembic upgrade head` and
the running app can never disagree about which database is being migrated.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from house_cost.config import get_settings
from house_cost.db import create_engine
from house_cost.models import Base, UtcDateTime

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _render_item(obj_type: str, obj: object, autogen_context: object) -> str | bool:  # noqa: ARG001
    """Render UtcDateTime as the plain DateTime it is built on.

    A migration has to keep running years later, and one that imports an application class stops
    working when that class moves. At the DDL level UtcDateTime is exactly ``sa.DateTime()``.

    Everything else returns False, Alembic's "use the default rendering"; None would render the
    item as an empty string.
    """
    if obj_type == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime()"
    return False


def _run(connection: Connection) -> None:
    """Apply migrations on a live connection.

    ``render_as_batch`` is required for SQLite, which cannot ALTER a column or a constraint: batch
    mode copies the table instead.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Apply migrations against the configured database."""
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run)
    finally:
        await engine.dispose()


asyncio.run(run_migrations_online())
