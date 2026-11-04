from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import quote

from .i18n import Text


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
        status_label=Text(f"perks.status_{status}"),
        description=_perk_description(key, status),
        guidance=Text("perks.discord_guidance") if is_discord else "",
        settings_url="https://www.fanbox.cc/user/settings" if is_discord else None,
        settings_label=Text("perks.discord_settings") if is_discord else None,
        action_url=(
            _creator_plans_url(creator_id)
            if is_discord and status == "accessible" else None
        ),
        action_label=Text("perks.discord_open") if is_discord and status == "accessible" else None,
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
        return Text("perks.discord_label")
    return _safe_text(fallback, fallback="") or Text("perks.other_label")


def _perk_description(key: str, status: PerkStatus) -> Text:
    return Text(f"perks.{'discord' if key == 'discord' else 'other'}_{status}")


def _creator_plans_url(creator_id: str) -> str | None:
    safe_creator = _safe_text(creator_id, fallback="")
    if not safe_creator:
        return None
    return f"https://www.fanbox.cc/@{quote(safe_creator, safe='')}/plans"


def _safe_text(value: Any, *, fallback: str) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or "")).strip()
    return text[:120] or fallback
