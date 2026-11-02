"""Runtime configuration, read from the environment.

Built on jigkit's ``AppSettings``, which supplies the data directory, the database URL, the log
level, ``PUBLIC_URL``, ``COOKIE_SECURE``, ``FORWARDED_ALLOW_IPS``, ``TZ``, the scheduler switch,
and the rules every app shares: a blank variable means unset, and a secret can be given as
``X`` or ``X_FILE`` but not both.
"""

from functools import lru_cache
from pathlib import Path

from jigkit.settings import AppSettings
from pydantic import AliasChoices, Field


class Settings(AppSettings):
    """Everything the application reads from its environment."""

    database_filename = "house-cost.db"

    login_attempts_per_minute: int = 10
    # The largest file accepted as an attachment.
    max_upload_bytes: int = 20 * 1024 * 1024

    # The daily backup: from what time of day, and how many daily snapshots are kept.
    backup_time: str = Field("03:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    backups_kept: int = Field(14, ge=1)
    # The scheduled work runs inside the app every ten minutes; tests turn it off and call it.
    scheduler_tick_seconds: int = Field(600, ge=1)

    # How notifications are sent, by Apprise URLs without a recipient: a person's email address
    # is added to the mail URL as its "to", their phone number to the Signal URL's path. A
    # channel left unset is not offered.
    notify_email_url: str | None = None
    notify_signal_url: str | None = None
    # The country a phone number typed without one is in: "912 345 678" is +351 912 345 678.
    phone_country_code: str = Field("351", pattern=r"^\d{1,3}$")

    # Claude, for reading bills no parser knows, contracts' terms and questions about documents.
    # Off without a key; the key can instead be read from a file, such as a Docker secret.
    anthropic_api_key: str | None = None
    anthropic_api_key_file: Path | None = None
    claude_model: str = "claude-opus-5-5"

    # The commit the image was built from, which the Dockerfile records; unset outside an image.
    revision: str | None = Field(
        None, validation_alias=AliasChoices("HOUSE_COST_REVISION", "revision")
    )

    @property
    def claude_key(self) -> str | None:
        """The Anthropic API key, from the variable or its file (jigkit reads the file)."""
        return self.anthropic_api_key.strip() if self.anthropic_api_key else None

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
