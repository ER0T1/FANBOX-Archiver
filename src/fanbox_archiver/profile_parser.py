from __future__ import annotations

from typing import Any

from .models import CreatorProfile, CreatorProfileItem


class CreatorProfileParser:
    """Normalize creator.get without exposing its unstable payload to readers."""

    def parse(self, payload: dict[str, Any], creator_id: str) -> CreatorProfile:
        body = payload.get("body")
        if not isinstance(body, dict):
            raise ValueError("creator.get 回應缺少 body")
        actual_id = str(body.get("creatorId") or creator_id).strip()
        if not actual_id:
            raise ValueError("creator.get 回應缺少 creatorId")
        user = body.get("user") if isinstance(body.get("user"), dict) else {}
        items = body.get("profileItems")
        parse_warnings: list[str] = []
        if not user.get("name") and not body.get("creatorName"):
            parse_warnings.append("Creator Profile 缺少創作者名稱，已使用 Creator ID。")
        if items is not None and not isinstance(items, list):
            parse_warnings.append("Creator Profile 的 profileItems 不是陣列，已略過。")
        elif isinstance(items, list):
            invalid = sum(not isinstance(item, dict) for item in items)
            if invalid:
                parse_warnings.append(f"Creator Profile 有 {invalid} 個無效 profile item，已略過。")
        profile = CreatorProfile(
            creator_id=actual_id,
            name=self._text(user.get("name") or body.get("creatorName") or actual_id),
            description=self._text(body.get("description")),
            icon_url=self._url(user.get("iconUrl") or body.get("iconUrl")),
            cover_url=self._url(body.get("coverImageUrl")),
            profile_items=[
                self._item(item) for item in (items if isinstance(items, list) else [])
                if isinstance(item, dict)
            ],
            has_adult_content=bool(body.get("hasAdultContent", False)),
            is_accepting_request=bool(body.get("isAcceptingRequest", False)),
            is_stopped=bool(
                body.get("isStopped", body.get("creatorAccountStopped", False))
            ),
            fanbox_url=f"https://www.fanbox.cc/@{actual_id}",
            parse_warnings=parse_warnings,
            raw=body,
        )
        profile.content_fingerprint = profile.calculate_fingerprint()
        return profile

    def _item(self, item: dict[str, Any]) -> CreatorProfileItem:
        value = item.get("value") if isinstance(item.get("value"), dict) else {}
        return CreatorProfileItem(
            item_id=self._text(item.get("id") or value.get("id")),
            type=self._text(item.get("type") or "unknown"),
            label=self._text(item.get("label") or item.get("title") or value.get("label")),
            url=self._url(item.get("url") or value.get("url")),
            description=self._text(
                item.get("description") or item.get("text") or value.get("description")
                or value.get("text")
            ),
            image_url=self._url(item.get("imageUrl") or value.get("imageUrl")),
        )

    @staticmethod
    def _text(value: Any) -> str:
        return "" if value is None else str(value).replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def _url(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None
