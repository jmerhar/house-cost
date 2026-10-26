"""Runtime configuration, read from the environment."""

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Everything the application reads from its environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    # Where all mutable state lives: the database, uploaded files and backups. One directory means
    # a deployment has exactly one thing to persist.
    data_dir: Path = Path("data")
    database_url: str | None = None

    log_level: str = "INFO"

    # The address people open the app at, behind its reverse proxy (https://costs.example.com).
    # Writes whose Origin is neither this nor the request's own host are refused.
    public_url: str | None = None
    # Forces the session cookie's Secure flag on or off. Unset, it follows the request's scheme,
    # which uvicorn takes from X-Forwarded-Proto when the proxy is one it trusts.
    cookie_secure: bool | None = None
    # The proxies whose X-Forwarded-For and X-Forwarded-Proto are believed, as uvicorn's
    # forwarded_allow_ips takes them: addresses or networks. Behind Docker's port publishing the
    # proxy arrives from the bridge gateway, which the compose file adds. Never "*": uvicorn then
    # believes the leftmost address, which the client wrote itself.
    forwarded_allow_ips: str = "127.0.0.1"
    login_attempts_per_minute: int = 10
    # The largest file accepted as an attachment.
    max_upload_bytes: int = 20 * 1024 * 1024

    # Where the house is, which decides when the day's backup and reminders are due. Read from TZ,
    # which the container's clock follows too.
    timezone: str = Field("UTC", validation_alias="TZ")
    # The daily backup: from what time of day, and how many daily snapshots are kept.
    backup_time: str = Field("03:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    backups_kept: int = Field(14, ge=1)
    # The scheduled work runs inside the app; tests turn it off and call it themselves.
    scheduler_enabled: bool = True
    scheduler_tick_seconds: int = 600

    # Where the built single-page app is served from. Absent, the API runs on its own, which is
    # how the dev stack works (Vite serves the app and proxies /api).
    static_dir: Path | None = None

    @field_validator("cookie_secure", mode="before")
    @classmethod
    def _blank_flag_is_unset(cls, value: object) -> object:
        """An empty ``COOKIE_SECURE``, as compose passes an unset one, means "follow the scheme"."""
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, value: str) -> str:
        """A time zone the scheduler can use, so a typo stops the app at startup."""
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"unknown time zone {value!r}") from error
        return value

    @model_validator(mode="after")
    def _blank_means_unset(self) -> Settings:
        """Treat an empty value as absent.

        Compose writes ``VAR: ${VAR:-}`` for an optional setting, so an unset variable arrives as
        an empty string. Left alone, an empty ``static_dir`` becomes ``Path(".")``, a real
        directory, and the application would serve its own working directory as the interface.
        """
        for field in ("static_dir", "database_url", "public_url"):
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

    @property
    def backups_dir(self) -> Path:
        """Where the daily snapshots of the database are kept."""
        return self.data_dir / "backups"

    @property
    def files_dir(self) -> Path:
        """Where attached files are kept, each under its SHA-256."""
        return self.data_dir / "files"


@lru_cache
def get_settings() -> Settings:
    """The process-wide settings, read once."""
    return Settings()
