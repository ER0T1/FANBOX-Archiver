from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal
import os
import re
import tempfile

import yaml
from pydantic import BaseModel, Field, field_validator


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


class ScheduleConfig(BaseModel):
    """Automatic backup schedule; times are always Asia/Taipei (no DST, host independent)."""

    enabled: bool = False
    frequency: Literal["daily", "weekly", "monthly"] = "daily"
    interval: int = Field(default=1, ge=1, le=30)
    weekday: int = Field(default=0, ge=0, le=6)
    month_day: int = Field(default=1, ge=1, le=31)
    time: str = "03:00"
    start_date: date | None = None
    creators: list[str] = Field(default_factory=list, max_length=100)
    timezone: Literal["Asia/Taipei"] = "Asia/Taipei"

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", value.strip())
        if not match:
            raise ValueError("排程時間必須是 HH:MM（24 小時制）")
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
            raise ValueError("不支援的日誌等級")
        return value


class AppConfig(BaseModel):
    auth: AuthConfig = AuthConfig()
    storage: StorageConfig = StorageConfig()
    download: DownloadConfig = DownloadConfig()
    markdown: MarkdownConfig = MarkdownConfig()
    sync: SyncConfig = SyncConfig()
    backup_defaults: BackupDefaultsConfig = BackupDefaultsConfig()
    schedule: ScheduleConfig = ScheduleConfig()
    logging: LoggingConfig = LoggingConfig()

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        data: dict[str, Any] = {}
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
        config = cls.model_validate(data)
        base = path.resolve().parent
        if not config.auth.profile_dir.is_absolute():
            config.auth.profile_dir = (base / config.auth.profile_dir).resolve()
        if not config.storage.output_dir.is_absolute():
            config.storage.output_dir = (base / config.storage.output_dir).resolve()
        if not config.storage.database.is_absolute():
            config.storage.database = (base / config.storage.database).resolve()
        return config

    def editable_dict(self) -> dict[str, Any]:
        value = self.model_dump(mode="json")
        return {
            "download": value["download"],
            "sync": value["sync"],
            "backup_defaults": value["backup_defaults"],
            "schedule": value["schedule"],
            "markdown": value["markdown"],
            "logging": value["logging"],
        }

    def with_editable_patch(self, patch: dict[str, Any]) -> "AppConfig":
        merged = self.model_dump(mode="python")
        for section, values in patch.items():
            if section not in {"download", "sync", "backup_defaults", "schedule", "markdown", "logging"}:
                raise ValueError(f"不允許修改設定區段：{section}")
            merged[section] = {**merged[section], **values}
        return type(self).model_validate(merged)

    @staticmethod
    def save_editable(path: Path, config: "AppConfig", patch: dict[str, Any]) -> None:
        raw: dict[str, Any] = config.model_dump(mode="json")
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
            if not isinstance(loaded, dict):
                raise ValueError("設定檔根節點必須是物件")
            raw = loaded
        editable = config.editable_dict()
        for section in patch:
            raw[section] = editable[section]
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

