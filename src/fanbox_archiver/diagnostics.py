"""Read-only facts for the About & diagnostics section, and opening fixed local folders.

Nothing here reads or reports cookies, tokens, account names or the sign-in browser
profile. Folders are chosen from a fixed set of names; callers never pass a path.
"""

from __future__ import annotations

import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import Literal

from . import __version__
from .config import AppConfig
from .database import SCHEMA_VERSION
from .timestamps import display_zone
from .windows_task import DESKTOP_EXE_ENV

# Set by the desktop shell when it starts the sidecar.
DESKTOP_VERSION_ENV = "FANBOX_ARCHIVER_DESKTOP_VERSION"
DESKTOP_LOG_DIR_ENV = "FANBOX_ARCHIVER_DESKTOP_LOG_DIR"

FolderTarget = Literal["archive", "archive_logs", "desktop_logs"]


def folder_path(config: AppConfig, target: FolderTarget) -> Path | None:
    if target == "archive":
        return config.storage.output_dir.resolve()
    if target == "archive_logs":
        return (config.storage.output_dir / "logs").resolve()
    desktop_logs = os.environ.get(DESKTOP_LOG_DIR_ENV)
    return Path(desktop_logs).resolve() if desktop_logs else None


def can_open_folders() -> bool:
    if os.name == "nt":
        return True
    return shutil.which("open" if sys.platform == "darwin" else "xdg-open") is not None


def open_folder(path: Path) -> None:
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def database_schema_version(database: Path) -> int | None:
    if not database.is_file():
        return None
    try:
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            row = db.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    except sqlite3.Error:
        return None
    return int(row[0]) if row and row[0] is not None else None


def collect(config: AppConfig, config_path: Path | None) -> dict:
    desktop = bool(os.environ.get(DESKTOP_EXE_ENV))
    folders = {target: folder_path(config, target) for target in ("archive", "archive_logs", "desktop_logs")}
    info = {
        "app_version": __version__,
        "mode": "desktop" if desktop else "browser",
        "desktop_version": os.environ.get(DESKTOP_VERSION_ENV) if desktop else None,
        "python_version": platform.python_version(),
        "os": platform.platform(),
        "schema": {
            "database": database_schema_version(config.storage.database),
            "supported": SCHEMA_VERSION,
        },
        "timezone": display_zone().name,
        "paths": {
            "config": str(config_path) if config_path else None,
            "archive": str(folders["archive"]),
            "database": str(config.storage.database.resolve()),
            "archive_logs": str(folders["archive_logs"]),
            "desktop_logs": str(folders["desktop_logs"]) if folders["desktop_logs"] else None,
        },
        "folders": {target: bool(path and path.is_dir()) for target, path in folders.items()},
        "can_open_folders": can_open_folders(),
    }
    info["text"] = diagnostics_text(info)
    return info


def diagnostics_text(info: dict) -> str:
    schema = info["schema"]
    paths = info["paths"]
    lines = [
        "FANBOX Archiver 診斷資訊",
        f"程式版本：{info['app_version']}",
        f"執行方式：{'桌面版 ' + str(info['desktop_version'] or '（版本不明）') if info['mode'] == 'desktop' else '瀏覽器版'}",
        f"資料庫 schema：{schema['database'] if schema['database'] is not None else '無法讀取'}"
        f"（程式支援 {schema['supported']}）",
        f"Python：{info['python_version']}",
        f"作業系統：{info['os']}",
        f"時區：{info['timezone']}",
        f"設定檔：{paths['config'] or '未指定'}",
        f"封存目錄：{paths['archive']}",
        f"資料庫：{paths['database']}",
        f"封存日誌：{paths['archive_logs']}",
    ]
    if paths["desktop_logs"]:
        lines.append(f"桌面日誌：{paths['desktop_logs']}")
    return "\n".join(lines) + "\n"
