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


def test_upgrading_a_database_that_has_people_keeps_them(data_dir: Path) -> None:
    # Columns added later must have defaults for the rows already there, or a deployment with
    # data fails to upgrade while an empty test database does not.
    def alembic(*args: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND,
            env={"DATA_DIR": str(data_dir), "PATH": ""},
            check=True,
            capture_output=True,
        )

    alembic("upgrade", "0002")
    engine = create_engine(f"sqlite:///{data_dir / 'house-cost.db'}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO household (id, name, position, active, created_at, updated_at) "
                "VALUES (1, 'H', 0, 1, '2026-01-01', '2026-01-01')"
            )
            connection.exec_driver_sql(
                "INSERT INTO person (id, name, login, password_hash, role, household_id, active, "
                "created_at, updated_at) VALUES (1, 'P', 'p', 'x', 'admin', 1, 1, '2026-01-01', "
                "'2026-01-01')"
            )
        alembic("upgrade", "head")
        with engine.connect() as connection:
            row = connection.exec_driver_sql(
                "SELECT login, email, phone, notify_on FROM person"
            ).one()
    finally:
        engine.dispose()

    assert tuple(row) == ("p", "", "", "{}")
