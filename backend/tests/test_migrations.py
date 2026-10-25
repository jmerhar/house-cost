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
