from __future__ import annotations

from .i18n import LanguageSetting, Text

from datetime import date
from pathlib import Path
from typing import Any, Literal
import os
import re
import tempfile

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StorageConfig(BaseModel):
    output_dir: Path = Path("./FANBOX")
    database: Path = Path("./FANBOX/backup.db")


class AuthConfig(BaseModel):
    profile_dir: Path = Path("./.fanbox-browser")
    browser_channel: str = "chrome"


class DownloadConfig(BaseModel):
    original_images: bool = True
    download_attachments: bool = True
    download_cover: bool = True
    max_concurrent: int = Field(default=1, ge=1, le=1)
    retry_count: int = Field(default=3, ge=0, le=10)
    request_interval_seconds: float = Field(default=3.0, ge=1.0)
    resume: bool = True
    verify_sha256: bool = True
    timeout_seconds: float = Field(default=60.0, ge=5.0, le=600.0)


class MarkdownConfig(BaseModel):
    enabled: bool = True
    yaml_front_matter: bool = True
    relative_image_paths: bool = True
    preserve_original_order: bool = True


class SyncConfig(BaseModel):
    skip_completed: bool = True
    check_updates: bool = True
    preserve_deleted_posts: bool = True
    max_posts_per_run: int = Field(default=20, ge=1, le=100)
    supporting_only: bool = True
    rotate_creators: bool = True
    recent_unchanged_stop_count: int = Field(default=20, ge=1, le=500)


class BackupDefaultsConfig(BaseModel):
    dry_run: bool = False
    include_profile: bool = True
    include_fancard: bool = True


class ThemeColors(BaseModel):
    """Custom colour overrides per mode; names outside the allowlist or non-#rrggbb values are refused."""

    model_config = ConfigDict(extra="forbid")
    light: dict[str, str] = Field(default_factory=dict)
    dark: dict[str, str] = Field(default_factory=dict)

    @field_validator("light", "dark")
    @classmethod
    def validate_colors(cls, value: dict[str, str]) -> dict[str, str]:
        from .theme import normalize_colors

        return normalize_colors(value)


class DisplayConfig(BaseModel):
    """How times are shown and how schedule times are read: ``system`` or an IANA zone.

    ``theme`` is the colour mode of the reader and desktop app; ``system`` follows the
    operating system's light/dark setting.

    ``language`` picks the interface catalog: ``auto`` follows the system or browser language
    among the shipped catalogs, falling back to English; ``qps-ploc`` is the
    pseudo-locale used only for layout testing.
    """

    timezone: str = "system"
    theme: Literal["system", "dark", "light"] = "system"
    colors: ThemeColors = Field(default_factory=ThemeColors)
    language: LanguageSetting = "auto"

    @property
    def css_theme(self) -> str:
        """The page's ``data-theme`` value (``system`` is rendered as ``auto``)."""
        return "auto" if self.theme == "system" else self.theme

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        from .timestamps import is_valid_timezone

        value = value.strip()
        if not is_valid_timezone(value):
            raise ValueError(Text("config.timezone_unsupported", value=str(value)))
        return value


class ScheduleConfig(BaseModel):
    """Automatic backup schedule; times are read in the global display timezone."""

    enabled: bool = False
    frequency: Literal["daily", "weekly", "monthly"] = "daily"
    interval: int = Field(default=1, ge=1, le=30)
    weekday: int = Field(default=0, ge=0, le=6)
    month_day: int = Field(default=1, ge=1, le=31)
    time: str = "00:00"
    start_date: date | None = None
    creators: list[str] = Field(default_factory=list, max_length=100)
    # no_wake_battery_ok: never wake the PC, run on battery too; no_wake_ac_only: never
    # wake, wait for mains power; wake: wake a sleeping PC (Windows Task Scheduler).
    power: Literal["no_wake_battery_ok", "no_wake_ac_only", "wake"] = "no_wake_battery_ok"

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", value.strip())
        if not match:
            raise ValueError(Text("config.schedule_time_invalid"))
        return match.group(0)


class LoggingConfig(BaseModel):
    level: str = "INFO"
    write_to_file: bool = True
    keep_days: int = Field(default=30, ge=1, le=365)

    @field_validator("level")
    @classmethod
    def validate_level(cls, value: str) -> str:
        value = value.upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(Text("config.log_level_invalid"))
        return value


class AppConfig(BaseModel):
    auth: AuthConfig = AuthConfig()
    storage: StorageConfig = StorageConfig()
    download: DownloadConfig = DownloadConfig()
    markdown: MarkdownConfig = MarkdownConfig()
    sync: SyncConfig = SyncConfig()
    backup_defaults: BackupDefaultsConfig = BackupDefaultsConfig()
    schedule: ScheduleConfig = ScheduleConfig()
    display: DisplayConfig = DisplayConfig()
    logging: LoggingConfig = LoggingConfig()

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        data: dict[str, Any] = {}
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            data = cls._migrate_display_timezone(path, data)
        config = cls.model_validate(data)
        base = path.resolve().parent
        if not config.auth.profile_dir.is_absolute():
            config.auth.profile_dir = (base / config.auth.profile_dir).resolve()
        if not config.storage.output_dir.is_absolute():
            config.storage.output_dir = (base / config.storage.output_dir).resolve()
        if not config.storage.database.is_absolute():
            config.storage.database = (base / config.storage.database).resolve()
        return config

    @staticmethod
    def _migrate_display_timezone(path: Path, data: Any) -> Any:
        """Settings saved before the global timezone kept times in Asia/Taipei; preserve that."""
        if not isinstance(data, dict) or "display" in data:
            return data
        schedule = data.get("schedule")
        if not isinstance(schedule, dict) or schedule.get("timezone") != "Asia/Taipei":
            return data
        migrated = {**data, "display": {"timezone": "Asia/Taipei"}}
        try:
            AppConfig._write_yaml(path, migrated)
        except OSError:
            pass  # a read-only file still loads with the migrated value
        return migrated

    def editable_dict(self) -> dict[str, Any]:
        value = self.model_dump(mode="json")
        return {
            "download": value["download"],
            "sync": value["sync"],
            "backup_defaults": value["backup_defaults"],
            "schedule": value["schedule"],
            "display": value["display"],
            "markdown": value["markdown"],
            "logging": value["logging"],
        }

    def with_editable_patch(self, patch: dict[str, Any]) -> "AppConfig":
        merged = self.model_dump(mode="python")
        for section, values in patch.items():
            if section not in {"download", "sync", "backup_defaults", "schedule", "display", "markdown", "logging"}:
                raise ValueError(Text("config.section_not_editable", section=str(section)))
            merged[section] = {**merged[section], **values}
        return type(self).model_validate(merged)

    @staticmethod
    def save_editable(path: Path, config: "AppConfig", patch: dict[str, Any]) -> None:
        raw: dict[str, Any] = config.model_dump(mode="json")
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
            if not isinstance(loaded, dict):
                raise ValueError(Text("config.root_not_mapping"))
            raw = loaded
        editable = config.editable_dict()
        for section in patch:
            raw[section] = editable[section]
        AppConfig._write_yaml(path, raw)

    @staticmethod
    def _write_yaml(path: Path, raw: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                yaml.safe_dump(raw, handle, allow_unicode=True, sort_keys=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise

