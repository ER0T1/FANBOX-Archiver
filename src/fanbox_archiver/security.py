from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse


ALLOWED_PAGE_HOSTS = {"www.fanbox.cc", "fanbox.cc", "api.fanbox.cc"}
ALLOWED_DOWNLOAD_HOSTS = {
    "downloads.fanbox.cc",
    "pixiv.pximg.net",
    "fanbox.pixiv.net",
}
INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def validate_url(url: str, *, download: bool = False) -> str:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if download:
        host_allowed = hostname in ALLOWED_DOWNLOAD_HOSTS
    else:
        # FANBOX creator pages also use official vanity hosts such as
        # https://creator-id.fanbox.cc/posts/123.
        host_allowed = hostname in ALLOWED_PAGE_HOSTS or hostname.endswith(".fanbox.cc")
    if parsed.scheme != "https" or not hostname or not host_allowed:
        raise ValueError(f"不允許的 URL 主機或協定：{parsed.scheme}://{parsed.hostname or ''}")
    if parsed.username or parsed.password:
        raise ValueError("URL 不可包含登入資訊")
    return url


def safe_filename(name: str, *, fallback: str = "unnamed", max_length: int = 120) -> str:
    clean = INVALID_WINDOWS_CHARS.sub("_", name).strip(" .")
    if not clean:
        clean = fallback
    stem = clean.split(".", 1)[0].upper()
    if stem in WINDOWS_RESERVED:
        clean = f"_{clean}"
    if len(clean) > max_length:
        suffix = Path(clean).suffix[:16]
        clean = clean[: max_length - len(suffix)].rstrip(" .") + suffix
    return clean


def confined_path(root: Path, relative: Path) -> Path:
    root = root.resolve()
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ValueError("偵測到目錄穿越路徑")
    return target

