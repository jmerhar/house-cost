"""The migrations, checked against the models they are supposed to produce."""

import subprocess
import sys
from pathlib import Path

from jigkit.testing.migrations import MigrationProject
from sqlalchemy import create_engine

from house_cost.models import Base

BACKEND = Path(__file__).resolve().parents[1]


#: The backend, with its alembic.ini, as jigkit's migration checks run it.
PROJECT = MigrationProject(BACKEND, database_filename="house-cost.db")


def test_the_migrations_produce_exactly_the_schema_the_models_describe(data_dir: Path) -> None:
    # The other tests build their schema with create_all, so nothing else would notice a model
    # change that never got a migration. Fix a failure with `make revision m='what changed'`.
    PROJECT.assert_models_match(Base.metadata, data_dir)


def test_there_is_exactly_one_head() -> None:
    PROJECT.assert_single_head()


def test_rebuilding_any_table_keeps_the_rows_pointing_at_it(data_dir: Path, tmp_path: Path) -> None:
    # Every table something points at is rebuilt by a throwaway migration over one synthetic row
    # in every table; ON DELETE rules firing during the rebuild would lose rows.
    PROJECT.assert_parent_rebuilds_keep_children(
        Base.metadata,
        data_dir,
        tmp_path,
        # A settlement is between two different households, and an attachment belongs to a bill
        # or a settlement but not both: one attachment of each, so both parents are checked.
        extra_rows={
            "household": [{"id": 2, "name": "second", "position": 1}],
            "attachment": [{"id": 2, "bill_id": None, "settlement_id": 1}],
        },
        overrides={"settlement": {"to_id": 2}, "attachment": {"settlement_id": None}},
    )


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
