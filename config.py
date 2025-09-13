"""Configuration management for Arbor Calendar Sync."""

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


class Config:
    """Configuration manager for Arbor Calendar Sync."""

    def __init__(self, config_file: str | Path | None = None, env_file: str | Path | None = None) -> None:
        """
        Initialize configuration.

        Args:
            config_file: Path to configuration file. If None, uses default location.
            env_file: Path to .env file. If None, searches for .env in working directory and parent directories.
        """
        # Load environment variables from .env file
        load_dotenv(env_file)

        if config_file is None:
            config_dir = Path.home() / ".config" / "arbor-calendar-sync"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_file = config_dir / "config.json"

        self.config_file = Path(config_file)
        self._config: dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, encoding="utf-8") as f:
                    self._config = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                print(f"Warning: Could not load config file {self.config_file}: {e}")
                self._config = {}
        else:
            self._config = {}
            self._set_defaults()

    def _set_defaults(self) -> None:
        """Set default configuration values with environment variable overrides."""
        defaults = {
            "google_calendar": {
                "calendar_id": os.getenv("GOOGLE_CALENDAR_ID", "primary"),
                "credentials_path": os.getenv(
                    "GOOGLE_CREDENTIALS_PATH",
                    str(Path.home() / ".config" / "arbor-calendar-sync" / "credentials.json")
                ),
                "token_path": os.getenv(
                    "GOOGLE_TOKEN_PATH",
                    str(Path.home() / ".config" / "arbor-calendar-sync" / "token.json")
                ),
            },
            "sync": {
                "delete_orphaned_events": os.getenv("SYNC_DELETE_ORPHANED_EVENTS", "true").lower() == "true",
                "update_existing_events": os.getenv("SYNC_UPDATE_EXISTING_EVENTS", "true").lower() == "true",
                "batch_size": int(os.getenv("SYNC_BATCH_SIZE", "100")),
                "dry_run": os.getenv("SYNC_DRY_RUN", "false").lower() == "true",
            },
            "arbor": {
                "timezone": os.getenv("ARBOR_TIMEZONE", "Europe/London"),
                "calendar_base_url": os.getenv("ARBOR_BASE_URL", "https://tiffin-school.uk.arbor.sc"),
                "login_url": os.getenv("ARBOR_LOGIN_URL"),  # Will be constructed from base_url if not provided
                "calendar_url": os.getenv("ARBOR_CALENDAR_URL"),  # Will be constructed from base_url if not provided
                "username": os.getenv("ARBOR_USERNAME"),
                "password": os.getenv("ARBOR_PASSWORD"),
            },
            "academic_year": {
                "start_month": int(os.getenv("ACADEMIC_YEAR_START_MONTH", "9")),  # September
                "start_day": int(os.getenv("ACADEMIC_YEAR_START_DAY", "1")),
                "end_month": int(os.getenv("ACADEMIC_YEAR_END_MONTH", "7")),    # July
                "end_day": int(os.getenv("ACADEMIC_YEAR_END_DAY", "31")),
            },
        }

        for section, values in defaults.items():
            if section not in self._config:
                self._config[section] = values

    def save(self) -> None:
        """Save configuration to file."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2)
        except OSError as e:
            print(f"Warning: Could not save config file {self.config_file}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value.

        Args:
            key: Configuration key in dot notation (e.g., 'google_calendar.calendar_id')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        keys = key.split(".")
        value = self._config

        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value.

        Args:
            key: Configuration key in dot notation (e.g., 'google_calendar.calendar_id')
            value: Value to set
        """
        keys = key.split(".")
        config = self._config

        # Navigate to the parent dictionary
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        # Set the final value
        config[keys[-1]] = value

    @property
    def google_calendar_id(self) -> str:
        """Get Google Calendar ID, with environment variable override."""
        return os.getenv("GOOGLE_CALENDAR_ID") or self.get("google_calendar.calendar_id", "primary")

    @property
    def credentials_path(self) -> Path:
        """Get path to Google credentials file, with environment variable override."""
        path = (
            os.getenv("GOOGLE_CREDENTIALS_PATH") or
            self.get("google_calendar.credentials_path") or
            str(Path.home() / ".config" / "arbor-calendar-sync" / "credentials.json")
        )
        return Path(path)

    @property
    def token_path(self) -> Path:
        """Get path to Google token file, with environment variable override."""
        path = (
            os.getenv("GOOGLE_TOKEN_PATH") or
            self.get("google_calendar.token_path") or
            str(Path.home() / ".config" / "arbor-calendar-sync" / "token.json")
        )
        return Path(path)

    @property
    def delete_orphaned_events(self) -> bool:
        """Whether to delete events that are no longer in Arbor, with environment variable override."""
        env_val = os.getenv("SYNC_DELETE_ORPHANED_EVENTS")
        if env_val is not None:
            return env_val.lower() == "true"
        return self.get("sync.delete_orphaned_events", True)

    @property
    def update_existing_events(self) -> bool:
        """Whether to update existing events with changes, with environment variable override."""
        env_val = os.getenv("SYNC_UPDATE_EXISTING_EVENTS")
        if env_val is not None:
            return env_val.lower() == "true"
        return self.get("sync.update_existing_events", True)

    @property
    def batch_size(self) -> int:
        """Batch size for Google Calendar operations, with environment variable override."""
        env_val = os.getenv("SYNC_BATCH_SIZE")
        if env_val is not None:
            return int(env_val)
        return self.get("sync.batch_size", 100)

    @property
    def arbor_timezone(self) -> str:
        """Timezone for Arbor events, with environment variable override."""
        return os.getenv("ARBOR_TIMEZONE") or self.get("arbor.timezone", "Europe/London")

    @property
    def arbor_base_url(self) -> str:
        """Base URL for Arbor API, with environment variable override."""
        return os.getenv("ARBOR_BASE_URL") or self.get("arbor.calendar_base_url", "https://tiffin-school.uk.arbor.sc")

    @property
    def arbor_login_url(self) -> str:
        """Login URL for Arbor, constructed from base URL if not specified."""
        env_url = os.getenv("ARBOR_LOGIN_URL")
        if env_url:
            return env_url
        config_url = self.get("arbor.login_url")
        if config_url:
            return config_url
        return f"{self.arbor_base_url}/auth/login"

    @property
    def arbor_calendar_url(self) -> str:
        """Calendar API URL for Arbor, constructed from base URL if not specified."""
        env_url = os.getenv("ARBOR_CALENDAR_URL")
        if env_url:
            return env_url
        config_url = self.get("arbor.calendar_url")
        if config_url:
            return config_url
        return f"{self.arbor_base_url}/calendar-entry/list-static/format/json/"

    @property
    def arbor_username(self) -> str | None:
        """Get Arbor username, with environment variable override."""
        return os.getenv("ARBOR_USERNAME") or self.get("arbor.username")

    @property
    def arbor_password(self) -> str | None:
        """Get Arbor password, with environment variable override."""
        return os.getenv("ARBOR_PASSWORD") or self.get("arbor.password")

    def is_configured(self) -> bool:
        """Check if basic configuration is complete."""
        return (
            self.credentials_path.exists() or
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS") is not None
        )


# Global configuration instance
config = Config()
