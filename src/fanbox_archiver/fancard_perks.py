from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import quote


PerkStatus = Literal["accessible", "inaccessible", "unavailable", "available", "unknown"]


@dataclass(frozen=True, slots=True)
class FanCardPerk:
    key: str
    label: str
    status: PerkStatus
    status_label: str
    description: str
    guidance: str
    settings_url: str | None
    settings_label: str | None
    action_url: str | None
    action_label: str | None
    available: bool | None
    supporter_accessible: bool | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_STATUS_LABELS: dict[PerkStatus, str] = {
    "accessible": "目前可使用",
    "inaccessible": "目前無法使用",
    "unavailable": "目前未提供",
    "available": "提供中，存取狀態未知",
    "unknown": "狀態未知",
}


def normalize_fancard_perks(value: Any, *, creator_id: str = "") -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        perk.as_dict()
        for item in value
        if (perk := _normalize_perk(item, creator_id=creator_id)) is not None
    ]


def _normalize_perk(value: Any, *, creator_id: str) -> FanCardPerk | None:
    if isinstance(value, str):
        key = _safe_text(value, fallback="unknown").casefold()
        label = _perk_label(key, value)
        available = supporter_accessible = None
    elif isinstance(value, dict):
        raw_key = value.get("name") or value.get("type") or value.get("id")
        key = _safe_text(raw_key, fallback="unknown").casefold()
        label = _perk_label(key, value.get("title") or raw_key)
        available = value.get("available") if isinstance(value.get("available"), bool) else None
        supporter_accessible = (
            value.get("supporterAccessible")
            if isinstance(value.get("supporterAccessible"), bool) else None
        )
    else:
        return None

    status = _perk_status(available, supporter_accessible)
    is_discord = key == "discord"
    return FanCardPerk(
        key=key,
        label=label,
        status=status,
        status_label=_STATUS_LABELS[status],
        description=_perk_description(key, status),
        guidance="Discord 連結可在帳號設定中編輯。" if is_discord else "",
        settings_url="https://www.fanbox.cc/user/settings" if is_discord else None,
        settings_label="帳號設定" if is_discord else None,
        action_url=(
            _creator_plans_url(creator_id)
            if is_discord and status == "accessible" else None
        ),
        action_label="在 FANBOX 開啟 Discord" if is_discord and status == "accessible" else None,
        available=available,
        supporter_accessible=supporter_accessible,
    )


def _perk_status(
    available: bool | None, supporter_accessible: bool | None,
) -> PerkStatus:
    if available is False:
        return "unavailable"
    if supporter_accessible is True:
        return "accessible"
    if supporter_accessible is False:
        return "inaccessible"
    if available is True:
        return "available"
    return "unknown"


def _perk_label(key: str, fallback: Any) -> str:
    if key == "discord":
        return "加入 Discord 伺服器"
    return _safe_text(fallback, fallback="其他權益")


def _perk_description(key: str, status: PerkStatus) -> str:
    if key == "discord":
        messages = {
            "accessible": "連結 Discord 後，即可加入創作者準備的 Discord 伺服器並參與社群交流。",
            "inaccessible": "此方案包含 Discord 伺服器權益，但封存時的帳號連結狀態尚未符合使用條件。",
            "unavailable": "封存時此方案未提供 Discord 伺服器權益。",
            "available": "此方案提供 Discord 伺服器權益，但封存資料未記錄目前帳號是否可使用。",
            "unknown": "封存資料顯示此方案可能包含 Discord 伺服器權益，但沒有足夠狀態可判斷是否可使用。",
        }
        return messages[status]
    subject = "此權益"
    messages = {
        "accessible": f"{subject}已包含在方案中；封存資料未包含可安全重播的外部加入連結。",
        "inaccessible": f"{subject}存在，但封存時的支持者狀態無法使用。",
        "unavailable": f"封存時{subject}未提供。",
        "available": f"封存時{subject}可用，但支持者存取狀態未記錄。",
        "unknown": f"封存資料未提供{subject}的完整狀態；不推測是否可使用。",
    }
    return messages[status]


def _creator_plans_url(creator_id: str) -> str | None:
    safe_creator = _safe_text(creator_id, fallback="")
    if not safe_creator:
        return None
    return f"https://www.fanbox.cc/@{quote(safe_creator, safe='')}/plans"


def _safe_text(value: Any, *, fallback: str) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or "")).strip()
    return text[:120] or fallback
