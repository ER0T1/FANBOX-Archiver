from __future__ import annotations

from pathlib import Path
from typing import Any

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

