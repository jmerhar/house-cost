"""Runtime configuration, read from the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Everything the application reads from its environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Where all mutable state lives: the database, uploaded files and backups. One directory means
    # a deployment has exactly one thing to persist.
    data_dir: Path = Path("data")
    database_url: str | None = None

    log_level: str = "INFO"

    # Where the built single-page app is served from. Absent, the API runs on its own, which is
    # how the dev stack works (Vite serves the app and proxies /api).
    static_dir: Path | None = None

    @model_validator(mode="after")
    def _blank_means_unset(self) -> Settings:
        """Treat an empty value as absent.

        Compose writes ``VAR: ${VAR:-}`` for an optional setting, so an unset variable arrives as
        an empty string. Left alone, an empty ``static_dir`` becomes ``Path(".")``, a real
        directory, and the application would serve its own working directory as the interface.
        """
        for field in ("static_dir", "database_url"):
            value = getattr(self, field)
            if value is not None and str(value).strip() in ("", "."):
                object.__setattr__(self, field, None)
        return self

    @property
    def resolved_database_url(self) -> str:
        """The database URL, defaulting to a SQLite file inside the data directory."""
        if self.database_url:
            return self.database_url
        return f"sqlite+aiosqlite:///{self.data_dir / 'house-cost.db'}"


@lru_cache
def get_settings() -> Settings:
    """The process-wide settings, read once."""
    return Settings()
