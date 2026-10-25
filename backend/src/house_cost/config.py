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
    def files_dir(self) -> Path:
        """Where attached files are kept, each under its SHA-256."""
        return self.data_dir / "files"


@lru_cache
def get_settings() -> Settings:
    """The process-wide settings, read once."""
    return Settings()
