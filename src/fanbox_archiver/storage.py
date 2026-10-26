from __future__ import annotations

import json
import os
import tempfile
import shutil
import uuid
import time
from pathlib import Path

from .models import Asset, Post
from .security import confined_path, safe_filename


class BackupStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def post_dir(self, post: Post) -> Path:
        day = post.published_at.date().isoformat() if post.published_at else "unknown-date"
        creator = safe_filename(post.creator_id, fallback="unknown")
        folder = safe_filename(f"{day}_{post.post_id}")
        return confined_path(self.root, Path(creator) / folder)

    def prepare(self, post: Post) -> Path:
        target = self.post_dir(post)
        for name in ("images", "files", "cover"):
            confined_path(target, Path(name)).mkdir(parents=True, exist_ok=True)
        return target

    def version_dir(self, post: Post, version_number: int) -> Path:
        return confined_path(self.post_dir(post), Path("versions") / f"v{version_number:04d}")

    def prepare_version(self, post: Post, version_number: int) -> tuple[Path, Path]:
        final = self.version_dir(post, version_number)
        temp = confined_path(final.parent, Path(f".{final.name}.{uuid.uuid4().hex}.tmp"))
        for name in ("images", "files", "cover"):
            (temp / name).mkdir(parents=True, exist_ok=True)
        return temp, final

    @staticmethod
    def publish_version(temp: Path, final: Path) -> None:
        final.parent.mkdir(parents=True, exist_ok=True)
        old = final.with_name(f".{final.name}.replaced")
        if old.exists():
            shutil.rmtree(old)
        if final.exists():
            BackupStorage._replace_with_retry(final, old)
        try:
            BackupStorage._replace_with_retry(temp, final)
        except BaseException:
            if old.exists() and not final.exists():
                BackupStorage._replace_with_retry(old, final)
            raise
        shutil.rmtree(old, ignore_errors=True)

    @staticmethod
    def _replace_with_retry(source: Path, target: Path) -> None:
        for attempt in range(6):
            try:
                os.replace(source, target)
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.25 * (2 ** attempt))

    @staticmethod
    def link_or_copy(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)

    def update_latest_alias(self, post: Post, version_dir: Path) -> None:
        root = self.post_dir(post)
        root.mkdir(parents=True, exist_ok=True)
        for source in version_dir.rglob("*"):
            if not source.is_file() or source.name == "manifest.json":
                continue
            relative = source.relative_to(version_dir)
            target = confined_path(root, relative)
            temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            self.link_or_copy(source, temporary)
            os.replace(temporary, target)

    def absolute_asset_path(self, post: Post, asset: Asset, *, base: Path | None = None) -> Path:
        if not asset.local_path:
            raise ValueError("資源尚未指派本機路徑")
        return confined_path(base or self.post_dir(post), Path(asset.local_path))

    def assign_asset_paths(self, post: Post) -> None:
        image_number = 0
        used_files: set[str] = set()
        for asset in post.assets:
            if asset.type == "image":
                image_number += 1
                suffix = Path(asset.original_name or "").suffix.lower() or Path(asset.url.split("?", 1)[0]).suffix.lower() or ".bin"
                asset.local_path = f"images/{image_number:03d}{suffix}"
            else:
                original = safe_filename(asset.original_name or f"asset-{asset.asset_id}")
                candidate = original
                if candidate.casefold() in used_files:
                    stem, suffix = Path(original).stem, Path(original).suffix
                    candidate = safe_filename(f"{stem}_{asset.asset_id}{suffix}")
                used_files.add(candidate.casefold())
                asset.local_path = f"files/{candidate}"
        if post.cover:
            suffix = Path(post.cover.original_name or "").suffix.lower() or Path(post.cover.url.split("?", 1)[0]).suffix.lower() or ".bin"
            post.cover.local_path = f"cover/cover{suffix}"

    @staticmethod
    def atomic_write_text(path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise

    @staticmethod
    def atomic_write_bytes(path: Path, value: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise

    def write_post_json(self, post: Post) -> Path:
        path = self.post_dir(post) / "post.json"
        value = json.dumps(post.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        self.atomic_write_text(path, value)
        return path

