from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

import hashlib
import json

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
    parse_warnings: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    content_fingerprint: str | None = None


class CreatorProfileItem(BaseModel):
    item_id: str = ""
    type: str = "unknown"
    label: str = ""
    url: str | None = None
    description: str = ""
    image_url: str | None = None
    image_path: str | None = None
    image_sha256: str | None = None


class CreatorProfile(BaseModel):
    creator_id: str
    name: str
    description: str = ""
    icon_url: str | None = None
    cover_url: str | None = None
    profile_items: list[CreatorProfileItem] = Field(default_factory=list)
    has_adult_content: bool = False
    is_accepting_request: bool = False
    is_stopped: bool = False
    fanbox_url: str
    parse_warnings: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    content_fingerprint: str = ""

    def calculate_fingerprint(self) -> str:
        value = self.model_dump(
            mode="json", exclude={"raw", "parse_warnings", "content_fingerprint"}
        )
        for item in value.get("profile_items", []):
            item.pop("image_path", None)
            item.pop("image_sha256", None)
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class VerificationIssue(BaseModel):
    path: str
    reason: str
    post_id: str | None = None
    asset_id: str | None = None

