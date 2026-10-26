from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class PostStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    RESTRICTED = "restricted"
    UNAVAILABLE = "unavailable"
    UPDATED = "updated"


class AssetStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    MISSING = "missing"
    CORRUPT = "corrupt"


class ContentBlock(BaseModel):
    type: Literal["paragraph", "heading", "quote", "image", "file", "embed", "separator", "raw"]
    text: str | None = None
    asset_id: str | None = None
    url: str | None = None
    name: str | None = None
    level: int | None = None
    styles: list["TextStyle"] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


class TextStyle(BaseModel):
    type: Literal["bold"]
    offset: int = Field(ge=0)
    length: int = Field(gt=0)


class Asset(BaseModel):
    asset_id: str
    type: Literal["image", "file", "cover", "video"]
    url: str
    original_name: str | None = None
    local_path: str | None = None
    width: int | None = None
    height: int | None = None
    size: int | None = None
    sha256: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    status: AssetStatus = AssetStatus.PENDING
    error: str | None = None


class Post(BaseModel):
    post_id: str
    creator_id: str
    creator_name: str = "unknown"
    creator_icon_url: str | None = None
    title: str
    published_at: datetime | None = None
    updated_at: datetime | None = None
    url: str
    post_type: str = "entry"
    fee_required: int | None = None
    tags: list[str] = Field(default_factory=list)
    blocks: list[ContentBlock] = Field(default_factory=list)
    assets: list[Asset] = Field(default_factory=list)
    cover: Asset | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    content_fingerprint: str | None = None


class VerificationIssue(BaseModel):
    path: str
    reason: str
    post_id: str | None = None
    asset_id: str | None = None

