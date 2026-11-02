"""The work the app does on its own: a daily copy of the database, and the daily reminders."""

import logging
from datetime import datetime, time
from pathlib import Path

from jigkit.scheduler import TickLoop
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from .config import Settings
from .db import session_scope
from .notify import Notifier
from .notify.events import contract_reminders, missing_bills

logger = logging.getLogger(__name__)


def local_now(settings: Settings) -> datetime:
    """The time where the house is, which decides when the day's work is due."""
    return datetime.now(settings.zone)


async def back_up(engine: AsyncEngine, directory: Path, today: str, keep: int) -> Path | None:
    """Copy the database to ``directory`` as today's snapshot, unless there is one, and keep only
    the ``keep`` newest.

    VACUUM INTO writes a consistent copy while the app goes on writing, which a plain file copy
    of a database in use cannot promise. A backup of the data directory then holds a snapshot it
    can restore even when it caught the live file mid-write.
    """
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"house-cost-{today}.db"
    if target.exists():
        return None
    partial = target.with_suffix(".partial")
    partial.unlink(missing_ok=True)
    async with engine.connect() as connection:
        raw = await connection.execution_options(isolation_level="AUTOCOMMIT")
        await raw.exec_driver_sql("VACUUM INTO ?", (str(partial),))
    partial.rename(target)
    for old in sorted(directory.glob("house-cost-*.db"), reverse=True)[keep:]:
        old.unlink()
    logger.info("backed the database up to %s", target.name)
    return target


class Scheduler:
    """Runs ``tick`` every few minutes for as long as the app runs, on jigkit's tick loop."""

    def __init__(
        self,
        settings: Settings,
        engine: AsyncEngine,
        sessionmaker: async_sessionmaker[AsyncSession],
        notifier: Notifier,
    ) -> None:
        self.settings = settings
        self.engine = engine
        self.sessionmaker = sessionmaker
        self.notifier = notifier
        self._last_reminded: str | None = None
        # Looked up on each tick rather than bound now, so a test can replace ``tick``.
        self._loop = TickLoop(
            lambda: self.tick(),
            settings.scheduler_tick_seconds,
            enabled=settings.scheduler_enabled,
            name="scheduler",
        )

    async def tick(self, now: datetime | None = None) -> None:
        """Do whatever is due: the day's backup once its time has come, and the day's reminders
        once a day."""
        now = now or local_now(self.settings)
        today = now.date().isoformat()
        hour, minute = (int(part) for part in self.settings.backup_time.split(":"))
        if now.time() >= time(hour, minute):
            await back_up(self.engine, self.settings.backups_dir, today, self.settings.backups_kept)
        if self._last_reminded != today:
            async with session_scope(self.sessionmaker) as db:
                await contract_reminders(db, self.notifier, now.date())
                await missing_bills(db, self.notifier, now.date())
            self._last_reminded = today

    @property
    def running(self) -> bool:
        """Whether the loop is ticking."""
        return self._loop.running

    def start(self) -> None:
        """Start the loop, when the settings allow it."""
        self._loop.start()

    async def stop(self) -> None:
        """Stop the loop and wait for it to end."""
        await self._loop.stop()
