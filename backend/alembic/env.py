"""Alembic environment.

Runs migrations through the application's own engine and settings, so `alembic upgrade head` and
the running app can never disagree about which database is being migrated.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, event

from house_cost.config import get_settings
from house_cost.db import create_engine, wants_sqlite_pragmas
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
    if connection.dialect.name == "sqlite":
        dangling = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if dangling:
            raise RuntimeError(f"the migrations left rows pointing at nothing: {dangling}")


def _without_foreign_keys(dbapi_connection: object, _record: object) -> None:
    """Turn SQLite's foreign keys off for the migrations.

    Batch mode rebuilds a table by copying it, dropping the original and renaming the copy. With
    foreign keys on, dropping the original runs every ON DELETE rule that points at it: rebuilding
    ``person`` would delete everyone's passkeys and sessions and empty the audit log's actors.
    The check after the migrations stands in for the enforcement left off during them.
    """
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute("PRAGMA foreign_keys=OFF")
    finally:
        cursor.close()


async def run_migrations_online() -> None:
    """Apply migrations against the configured database."""
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings)
    if wants_sqlite_pragmas(settings.resolved_database_url):
        # After the application's own pragmas, which turn foreign keys on for every connection.
        event.listen(engine.sync_engine, "connect", _without_foreign_keys)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run)
    finally:
        await engine.dispose()


asyncio.run(run_migrations_online())
