"""Settings read from the environment."""

from pathlib import Path

import pytest

from house_cost.config import Settings, get_settings


class TestBlankMeansUnset:
    @pytest.mark.parametrize("value", ["", " ", "."])
    def test_a_blank_static_dir_serves_no_frontend(self, value: str) -> None:
        # Compose passes an unset optional variable as an empty string; Path("") is ".", a real
        # directory the app would otherwise try to serve.
        assert Settings(static_dir=value).static_dir is None

    def test_a_blank_database_url_falls_back_to_the_data_directory(self, data_dir: Path) -> None:
        settings = Settings(data_dir=data_dir, database_url="")

        assert settings.resolved_database_url == f"sqlite+aiosqlite:///{data_dir}/house-cost.db"

    def test_a_blank_cookie_flag_follows_the_scheme(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COOKIE_SECURE", "")
        assert Settings().cookie_secure is None
        monkeypatch.setenv("COOKIE_SECURE", "false")
        assert Settings().cookie_secure is False

    def test_the_time_zone_is_read_from_tz(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TZ", "Europe/Lisbon")
        assert Settings().timezone == "Europe/Lisbon"
        monkeypatch.setenv("TZ", "Europe/Atlantis")
        with pytest.raises(ValueError, match="unknown time zone"):
            Settings()

    def test_a_real_value_is_kept(self, data_dir: Path) -> None:
        settings = Settings(static_dir=data_dir, database_url="sqlite+aiosqlite:///other.db")

        assert settings.static_dir == data_dir
        assert settings.resolved_database_url == "sqlite+aiosqlite:///other.db"


def test_settings_are_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path
) -> None:
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    get_settings.cache_clear()
    try:
        settings = get_settings()

        assert settings.data_dir == data_dir
        assert settings.log_level == "DEBUG"
        assert get_settings() is settings
    finally:
        get_settings.cache_clear()
