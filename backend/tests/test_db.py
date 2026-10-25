"""The engine, its SQLite settings, and the transaction helper."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import Integer, MetaData, String, func, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from house_cost.config import Settings
from house_cost.db import create_engine, create_sessionmaker, session_scope, wants_sqlite_pragmas
from house_cost.models import TimestampMixin, UtcDateTime


class Base(DeclarativeBase):
    """A base of its own, so this test's table never joins the application's schema."""

    metadata = MetaData()


class Note(TimestampMixin, Base):
    """A table that exists only in these tests."""

    __tablename__ = "test_note"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    body: Mapped[str] = mapped_column(String)


@pytest.fixture
async def sessionmaker(settings: Settings):
    engine = create_engine(settings)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_sessionmaker(engine)
    await engine.dispose()


async def test_sqlite_runs_with_foreign_keys_and_wal(settings: Settings) -> None:
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            foreign_keys = (await connection.execute(text("PRAGMA foreign_keys"))).scalar_one()
            journal = (await connection.execute(text("PRAGMA journal_mode"))).scalar_one()
    finally:
        await engine.dispose()

    assert foreign_keys == 1
    assert journal == "wal"


@pytest.mark.parametrize(
    ("url", "expected"),
    [("sqlite+aiosqlite:///x.db", True), ("postgresql+asyncpg://db/house", False)],
)
def test_only_sqlite_gets_sqlite_pragmas(url: str, expected: bool) -> None:
    assert wants_sqlite_pragmas(url) is expected


class TestSessionScope:
    async def test_commits_when_the_block_succeeds(self, sessionmaker) -> None:
        async with session_scope(sessionmaker) as session:
            session.add(Note(body="kept"))

        async with sessionmaker() as session:
            assert (await session.execute(select(func.count(Note.id)))).scalar_one() == 1

    async def test_rolls_back_when_the_block_raises(self, sessionmaker) -> None:
        with pytest.raises(RuntimeError):
            async with session_scope(sessionmaker) as session:
                session.add(Note(body="discarded"))
                await session.flush()
                raise RuntimeError

        async with sessionmaker() as session:
            assert (await session.execute(select(func.count(Note.id)))).scalar_one() == 0


class TestUtcDateTime:
    async def test_times_come_back_aware_and_in_utc(self, sessionmaker) -> None:
        lisbon_summer = timezone(timedelta(hours=1))
        async with session_scope(sessionmaker) as session:
            note = Note(body="x", created_at=datetime(2026, 7, 1, 13, 0, tzinfo=lisbon_summer))
            session.add(note)

        async with sessionmaker() as session:
            loaded = (await session.execute(select(Note))).scalar_one()

        assert loaded.created_at == datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
        assert loaded.created_at.tzinfo is UTC
        assert loaded.updated_at.tzinfo is UTC

    def test_a_naive_time_is_refused(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            UtcDateTime().process_bind_param(datetime(2026, 7, 1, 12, 0), None)

    def test_null_stays_null(self) -> None:
        assert UtcDateTime().process_bind_param(None, None) is None
        assert UtcDateTime().process_result_value(None, None) is None
