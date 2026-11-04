"""One-time cleanup of the offline static site that versions before v1.3.46 generated.

The static site was derived data (rebuildable from the archive), and it was removed in
v1.3.46-alpha. Only items that are certainly this program's output are deleted, and only
at the top level of the archive directory:

* ``_site/`` and ``._site.replaced/`` — must be real directories holding ``build.json``;
* ``._site.<32 hex>.tmp/`` — staging directories left by an interrupted index build;
* ``index.html`` — must be a regular file titled "FANBOX Archive" that loads ``_site/assets/``.

Anything else with those names, any symbolic link or Windows junction (at the top level or
inside the directory), and anything outside the archive is left alone and reported instead.
Failures (e.g. a file open in a browser) never stop the program; the next start retries.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path

from .archive_lock import ArchiveLock
from .config import AppConfig
from .logging_setup import get_logger

SITE_DIRS = ("_site", "._site.replaced")
STAGING_DIR = re.compile(r"^\._site\.[0-9a-f]{32}\.tmp$")
INDEX_FILE = "index.html"
_INDEX_MAX_BYTES = 5_000_000
_INDEX_MARKERS = ("<title>FANBOX Archive</title>", '"_site/assets/')


@dataclass
class LegacySiteCleanup:
    removed: list[str] = field(default_factory=list)
    # (name, reason) for items that look related but were not deleted.
    skipped: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def notices(self) -> list[str]:
        return [f"未刪除舊靜態網站項目「{name}」：{reason}" for name, reason in self.skipped + self.failed]

    def as_dict(self) -> dict:
        return {"removed": self.removed, "notices": self.notices}


def _is_link(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    # Junctions and other reparse points (Windows) are never followed or removed.
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _contains_link(directory: Path) -> bool:
    for current, dirs, files in os.walk(directory, followlinks=False):
        for name in dirs + files:
            if _is_link(Path(current) / name):
                return True
    return False


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root)
        return path.parent.resolve() == root
    except (OSError, ValueError):
        return False


def _generated_index(path: Path) -> bool:
    try:
        if not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size > _INDEX_MAX_BYTES:
            return False
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return all(marker in text for marker in _INDEX_MARKERS)


def remove_legacy_static_site(root: Path) -> LegacySiteCleanup:
    """Delete the old static-site output at the top of ``root``; see the module docstring."""
    result = LegacySiteCleanup()
    root = Path(root)
    if not root.is_dir() or _is_link(root):
        return result
    root = root.resolve()
    log = get_logger()
    candidates: list[tuple[Path, bool]] = [(root / name, True) for name in SITE_DIRS]
    try:
        candidates += [(entry, False) for entry in root.iterdir() if STAGING_DIR.fullmatch(entry.name)]
    except OSError:
        return result
    for path, needs_build_file in candidates:
        if not os.path.lexists(path):
            continue
        name = path.name
        if _is_link(path):
            result.skipped.append((name, "這是連結或 junction"))
        elif not path.is_dir() or not _inside(root, path):
            result.skipped.append((name, "不是封存目錄內的資料夾"))
        elif needs_build_file and not (path / "build.json").is_file():
            result.skipped.append((name, "缺少 build.json，可能不是本程式產生的"))
        elif _contains_link(path):
            result.skipped.append((name, "資料夾內含連結或 junction"))
        else:
            try:
                shutil.rmtree(path)
                result.removed.append(f"{name}/")
            except OSError as exc:
                result.failed.append((name, f"刪除失敗（{exc.__class__.__name__}），下次啟動再試"))
    index = root / INDEX_FILE
    if os.path.lexists(index):
        if _is_link(index):
            result.skipped.append((INDEX_FILE, "這是連結"))
        elif not _generated_index(index):
            result.skipped.append((INDEX_FILE, "內容不是本程式產生的索引入口"))
        else:
            try:
                index.unlink()
                result.removed.append(INDEX_FILE)
            except OSError as exc:
                result.failed.append((INDEX_FILE, f"刪除失敗（{exc.__class__.__name__}），下次啟動再試"))
    if result.removed:
        log.info("已刪除舊版離線靜態網站：%s", "、".join(result.removed))
    for notice in result.notices:
        log.warning(notice)
    return result


def cleanup_owned_archive(config: AppConfig, lock: ArchiveLock | None = None) -> LegacySiteCleanup:
    """Run the cleanup only while this process owns the archive (never beside another writer)."""
    root = config.storage.output_dir
    if lock is not None:
        return remove_legacy_static_site(root) if lock.held or lock.try_acquire() else LegacySiteCleanup()
    if not Path(root).is_dir():
        return LegacySiteCleanup()
    own = ArchiveLock(root)
    if not own.try_acquire():
        return LegacySiteCleanup()
    try:
        return remove_legacy_static_site(root)
    finally:
        own.release()
