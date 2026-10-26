from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from .parser import StructuredPostParser
from .security import validate_url


class AuthenticationError(RuntimeError):
    pass


class AccessRestrictedError(RuntimeError):
    pass


class RateLimitedError(RuntimeError):
    pass


class RemoteUnavailableError(RuntimeError):
    pass


@dataclass(slots=True)
class Creator:
    creator_id: str
    name: str


@dataclass(slots=True)
class PostSummary:
    post_id: str
    updated_at: str | None = None
    title: str = ""
    is_restricted: bool = False
    fee_required: int | None = None


class FanboxClient:
    API_ROOT = "https://api.fanbox.cc"

    def __init__(self, cookie: str | None = None, timeout: float = 60.0,
                 user_agent: str | None = None, request_interval: float = 3.0):
        self.cookie = cookie if cookie is not None else os.environ.get("FANBOX_COOKIE", "")
        headers = {
            "Accept": "application/json",
            "Origin": "https://www.fanbox.cc",
            "Referer": "https://www.fanbox.cc/",
            "User-Agent": user_agent or "FANBOX-Archiver/0.1 (+personal-backup; conservative-rate)",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        self.http = httpx.Client(headers=headers, timeout=timeout, follow_redirects=False)
        self.request_interval = max(0.0, request_interval)
        self._last_request = 0.0
        self.post_payload_fetcher: Callable[[str], dict[str, Any]] | None = None

    def __enter__(self) -> "FanboxClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.http.close()

    @staticmethod
    def post_id_from_url(url: str) -> str:
        validate_url(url)
        path = urlparse(url).path.rstrip("/").split("/")
        if len(path) < 2 or path[-2] != "posts" or not path[-1].isdigit():
            raise ValueError("投稿 URL 格式錯誤")
        return path[-1]

    def _get(self, path_or_url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = path_or_url if path_or_url.startswith("https://") else f"{self.API_ROOT}/{path_or_url.lstrip('/')}"
        validate_url(url)
        remaining = self.request_interval - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)
        self._last_request = time.monotonic()
        response = self.http.get(url, params=params)
        if response.status_code == 401:
            raise AuthenticationError("登入狀態已失效，請更新 FANBOX_COOKIE")
        if response.status_code == 403:
            raise AccessRestrictedError("目前帳號無權存取此內容")
        if response.status_code == 404:
            raise RemoteUnavailableError("遠端投稿不存在或目前無法取得")
        if response.status_code == 429:
            raise RateLimitedError("FANBOX 回傳 429；已停止，請稍後再試")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("API 回應格式不正確")
        return payload

    def post(self, url_or_id: str):
        post_id = url_or_id if url_or_id.isdigit() else self.post_id_from_url(url_or_id)
        payload = (self.post_payload_fetcher(post_id) if self.post_payload_fetcher
                   else self._get("post.info", {"postId": post_id}))
        return StructuredPostParser().parse(payload)

    def supporting_creators(self) -> list[Creator]:
        payload = self._get("plan.listSupporting")
        body = payload.get("body") or []
        if isinstance(body, dict):
            items = body.get("plans") or body.get("items") or []
        else:
            items = body
        result: list[Creator] = []
        seen: set[str] = set()
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            creator_id = str(item.get("creatorId") or item.get("creator_id") or "")
            if creator_id and creator_id not in seen:
                seen.add(creator_id)
                user = item.get("user") if isinstance(item.get("user"), dict) else {}
                result.append(Creator(
                    creator_id,
                    str(item.get("creatorName") or user.get("name") or creator_id),
                ))
        return result

    @staticmethod
    def creator_id(value: str) -> str:
        """Normalize a Creator ID, creator URL, or post URL."""
        value = value.strip()
        if not value:
            raise ValueError("Creator ID 不可為空")
        if "://" not in value:
            if any(char in value for char in "/?#@"):
                raise ValueError("Creator ID 格式錯誤")
            return value
        validate_url(value)
        parsed = urlparse(value)
        parts = [part for part in parsed.path.split("/") if part]
        if not parts or not parts[0].startswith("@") or len(parts[0]) == 1:
            raise ValueError("創作者 URL 格式錯誤")
        if len(parts) > 1 and not (len(parts) == 3 and parts[1] == "posts" and parts[2].isdigit()):
            raise ValueError("創作者 URL 格式錯誤")
        return parts[0][1:]

    def creator_post_pages(self, creator_id: str) -> list[str]:
        payload = self._get("post.paginateCreator", {"creatorId": creator_id})
        body = payload.get("body") or []
        if isinstance(body, dict):
            body = body.get("pageUrls") or body.get("items") or []
        return [str(page) for page in body if isinstance(page, str)]

    def creator_page(self, page_url: str) -> list[PostSummary]:
        payload = self._get(page_url)
        body = payload.get("body") or []
        if isinstance(body, dict):
            body = body.get("posts") or body.get("items") or []
        result: list[PostSummary] = []
        for item in body if isinstance(body, list) else []:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            result.append(PostSummary(
                post_id=str(item["id"]),
                updated_at=str(item.get("updatedDatetime") or item.get("updated_at") or "") or None,
                title=str(item.get("title") or ""),
                is_restricted=bool(item.get("isRestricted", False)),
                fee_required=(int(item["feeRequired"]) if item.get("feeRequired") is not None else None),
            ))
        return result

    def creator_post_ids(self, creator_id: str, limit: int = 20) -> list[str]:
        ids: list[str] = []
        for page in self.creator_post_pages(creator_id):
            if len(ids) >= limit:
                break
            for item in self.creator_page(page):
                ids.append(item.post_id)
                if len(ids) >= limit:
                    break
        return ids

    def verify_auth(self) -> bool:
        if not self.cookie:
            return False
        self.supporting_creators()
        return True

