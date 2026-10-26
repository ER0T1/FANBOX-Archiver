from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

import httpx
from PIL import Image, UnidentifiedImageError

from .models import Asset, AssetStatus
from .security import validate_url


class DownloadError(RuntimeError):
    pass


class DownloadAuthorizationError(DownloadError):
    pass


class DownloadRateLimitedError(DownloadError):
    pass


class AssetDownloader:
    def __init__(self, *, cookie: str = "", timeout: float = 60.0, retries: int = 3,
                 interval: float = 3.0, resume: bool = True, user_agent: str | None = None,
                 progress: Callable[[Asset, int, int | None], None] | None = None):
        headers = {
            "Referer": "https://www.fanbox.cc/",
            "User-Agent": user_agent or "FANBOX-Archiver/0.1 (+personal-backup; conservative-rate)",
        }
        if cookie:
            headers["Cookie"] = cookie
        self.http = httpx.Client(headers=headers, timeout=timeout, follow_redirects=False)
        self.retries = retries
        self.interval = interval
        self.resume = resume
        self.progress = progress
        self._last_request = 0.0

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "AssetDownloader":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def download(self, asset: Asset, target: Path) -> Asset:
        validate_url(asset.url, download=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        asset.status = AssetStatus.DOWNLOADING
        error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                self._wait()
                self._stream(asset, part)
                self._validate(asset, part)
                os.replace(part, target)
                asset.size = target.stat().st_size
                asset.sha256 = sha256_file(target)
                asset.status = AssetStatus.COMPLETED
                asset.error = None
                return asset
            except (httpx.HTTPError, OSError, DownloadError) as exc:
                if isinstance(exc, (DownloadAuthorizationError, DownloadRateLimitedError)):
                    asset.status = AssetStatus.FAILED
                    asset.error = str(exc)
                    raise
                error = exc
                if attempt < self.retries:
                    time.sleep(min(2 ** attempt, 10))
        asset.status = AssetStatus.FAILED
        asset.error = str(error)
        raise DownloadError(str(error))

    def _wait(self) -> None:
        remaining = self.interval - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)
        self._last_request = time.monotonic()

    def _stream(self, asset: Asset, part: Path, url: str | None = None, redirects: int = 0) -> None:
        if redirects > 3:
            raise DownloadError("下載重新導向次數過多")
        request_url = url or asset.url
        validate_url(request_url, download=True)
        existing = part.stat().st_size if self.resume and part.exists() else 0
        headers: dict[str, str] = {}
        if existing:
            headers["Range"] = f"bytes={existing}-"
            validator = asset.etag or asset.last_modified
            if validator:
                headers["If-Range"] = validator
        with self.http.stream("GET", request_url, headers=headers) as response:
            if response.status_code in {401, 403}:
                raise DownloadAuthorizationError(f"HTTP {response.status_code}：無權下載資源")
            if response.status_code == 429:
                raise DownloadRateLimitedError("HTTP 429：已停止本次備份，請稍後再試")
            if response.status_code in {301, 302, 303, 307, 308}:
                location = urljoin(request_url, response.headers.get("location", ""))
                validate_url(location, download=True)
                return self._stream(asset, part, location, redirects + 1)
            response.raise_for_status()
            append = existing > 0 and response.status_code == 206
            if append:
                content_range = response.headers.get("content-range", "")
                if not content_range.startswith(f"bytes {existing}-"):
                    raise DownloadError("伺服器回傳的續傳範圍不正確")
            mode = "ab" if append else "wb"
            if not append:
                existing = 0
            asset.etag = response.headers.get("etag")
            asset.last_modified = response.headers.get("last-modified")
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                raise DownloadError("下載結果是 HTML 錯誤頁")
            written = 0
            length = response.headers.get("content-length")
            total = (existing + int(length)) if length and append else (int(length) if length else None)
            with part.open(mode) as handle:
                for chunk in response.iter_bytes(1024 * 256):
                    if chunk:
                        handle.write(chunk)
                        written += len(chunk)
                        if self.progress:
                            self.progress(asset, existing + written, total)
                handle.flush()
                os.fsync(handle.fileno())
            if length and written != int(length):
                raise DownloadError(f"Content-Length 不符：預期 {length}，收到 {written}")

    @staticmethod
    def _validate(asset: Asset, path: Path) -> None:
        if not path.exists() or path.stat().st_size == 0:
            raise DownloadError("下載檔案為空")
        with path.open("rb") as handle:
            prefix = handle.read(256).lstrip().lower()
        if prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html"):
            raise DownloadError("下載內容疑似 HTML 錯誤頁")
        if asset.type in {"image", "cover"}:
            try:
                with Image.open(path) as image:
                    image.verify()
                with Image.open(path) as image:
                    width, height = image.size
                if asset.width and width != asset.width:
                    raise DownloadError(f"圖片寬度不符：預期 {asset.width}，收到 {width}")
                if asset.height and height != asset.height:
                    raise DownloadError(f"圖片高度不符：預期 {asset.height}，收到 {height}")
                asset.width, asset.height = width, height
            except UnidentifiedImageError as exc:
                raise DownloadError("不是有效圖片") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
