"""The migrations, checked against the models they are supposed to produce."""

import subprocess
import sys
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from house_cost.models import Base

BACKEND = Path(__file__).resolve().parents[1]


def test_the_migrations_produce_exactly_the_schema_the_models_describe(data_dir: Path) -> None:
    # The other tests build their schema with create_all, so nothing else would notice a model
    # change that never got a migration. Run as `alembic upgrade head` in a subprocess, exactly
    # as the container's entrypoint does, through the application's own env.py and settings.
    database = data_dir / "house-cost.db"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env={"DATA_DIR": str(data_dir), "PATH": ""},
        check=True,
        capture_output=True,
    )
    engine = create_engine(f"sqlite:///{database}")
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"compare_type": True, "render_as_batch": True}
            )
            differences = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert differences == [], (
        "the models and the migrations disagree; generate a migration with "
        "`make revision m='what changed'`"
    )


def test_there_is_exactly_one_head() -> None:
    # Two heads means two migrations claim the same parent, and `upgrade head` fails on a
    # deployment rather than in CI.
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))

    assert len(ScriptDirectory.from_config(config).get_heads()) == 1


def test_upgrading_a_database_with_data_keeps_all_of_it(data_dir: Path) -> None:
    # Columns added later must have defaults for the rows already there, and a migration that
    # rebuilds a table (SQLite's batch mode copies it, drops the original and renames the copy)
    # must not set off the ON DELETE rules of the tables pointing at it. An empty test database
    # notices neither, so this one has a person and the rows that depend on them.
    def alembic(*args: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND,
            env={"DATA_DIR": str(data_dir), "PATH": ""},
            check=True,
            capture_output=True,
        )

    alembic("upgrade", "0003")
    engine = create_engine(f"sqlite:///{data_dir / 'house-cost.db'}")
    try:
        with engine.begin() as connection:
            for statement in (
                "INSERT INTO household (id, name, position, active, created_at, updated_at) "
                "VALUES (1, 'H', 0, 1, '2026-01-01', '2026-01-01')",
                "INSERT INTO person (id, name, login, password_hash, role, household_id, active, "
                "created_at, updated_at) VALUES (1, 'P', 'p', 'x', 'admin', 1, 1, '2026-01-01', "
                "'2026-01-01')",
                "INSERT INTO session (id, token_hash, person_id, created_at, last_seen_at, "
                "expires_at, user_agent) VALUES (1, 'h', 1, '2026-01-01', '2026-01-01', "
                "'2027-01-01', 'Firefox')",
                "INSERT INTO passkey (id, person_id, credential_id, public_key, sign_count, "
                "transports, label, created_at) VALUES (1, 1, X'01', X'02', 0, '[]', 'Phone', "
                "'2026-01-01')",
                "INSERT INTO audit_event (id, at, person_id, action, entity, entity_id) "
                "VALUES (1, '2026-01-01', 1, 'create', 'person', 1)",
            ):
                connection.exec_driver_sql(statement)
        alembic("upgrade", "head")
        with engine.connect() as connection:
            person = connection.exec_driver_sql(
                "SELECT login, email, phone, notify_on FROM person"
            ).one()
            kept = [
                connection.exec_driver_sql(query).scalar_one()
                for query in (
                    "SELECT count(*) FROM session WHERE person_id = 1",
                    "SELECT count(*) FROM passkey WHERE person_id = 1",
                    "SELECT count(*) FROM audit_event WHERE person_id = 1",
                )
            ]
    finally:
        engine.dispose()

    assert tuple(person) == ("p", "", "", "{}")
    assert kept == [1, 1, 1]
