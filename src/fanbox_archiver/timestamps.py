"""Shared presentation of persisted time points in the configured display timezone.

The display timezone is one global setting: ``system`` (the computer's zone,
resolved here to an IANA name) or an IANA name such as ``Asia/Tokyo``. Stored
values always keep their own UTC offset and are never rewritten; only how they
are shown changes. Values without an explicit offset are never guessed; callers
show them as-is with an "unknown timezone" marker instead. Times are always
24-hour ``HH:MM``. DST transitions get no special handling (a known limitation).
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from functools import lru_cache
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

SYSTEM = "system"
DEVELOPMENT_TIMEZONE = "Asia/Taipei"
TAIPEI = ZoneInfo(DEVELOPMENT_TIMEZONE)
# FANBOX bills and changes Fan Cards on Japanese calendar months; this is data semantics,
# so it never follows the display timezone.
FANBOX_TIMEZONE = ZoneInfo("Asia/Tokyo")
UNKNOWN_ZONE_SUFFIX = "（時區未標示）"
COMMON_TIMEZONES = (
    "Asia/Taipei", "Asia/Tokyo", "Asia/Seoul", "Asia/Shanghai", "Asia/Hong_Kong", "Asia/Singapore",
    "Asia/Bangkok", "Australia/Sydney", "Europe/London", "Europe/Paris", "Europe/Berlin",
    "America/New_York", "America/Chicago", "America/Los_Angeles", "UTC",
)


@dataclass(frozen=True, slots=True)
class DisplayZone:
    setting: str
    """``system`` or the IANA name the user chose."""
    name: str
    """The effective zone: an IANA name, or ``Etc/GMT±N`` when the system zone has no known name."""
    tz: tzinfo
    notice: str | None = None


@lru_cache(maxsize=1)
def timezone_names() -> tuple[str, ...]:
    return tuple(sorted(name for name in available_timezones() if "/" in name or name == "UTC"))


def is_valid_timezone(name: str) -> bool:
    if name == SYSTEM:
        return True
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return name in timezone_names()


def _system_timezone_name() -> str | None:
    try:
        import tzlocal

        return tzlocal.get_localzone_name()
    except Exception:  # noqa: BLE001 - any failure falls back to the current offset
        return None


def _offset_zone() -> DisplayZone:
    seconds = _time.localtime().tm_gmtoff or 0
    hours, remainder = divmod(seconds, 3600)
    name = "UTC" if seconds == 0 else f"Etc/GMT{'-' if hours >= 0 else '+'}{abs(hours)}"
    if remainder or not is_valid_timezone(name):
        name, zone = "UTC", timezone(timedelta(seconds=seconds))
    else:
        zone = ZoneInfo(name)
    return DisplayZone(SYSTEM, name, zone, "無法辨識電腦的時區名稱，暫以目前的 UTC 時差顯示；可在設定頁改選時區。")


def resolve_timezone(setting: str, *, system_name: Callable[[], str | None] | None = None) -> DisplayZone:
    if setting != SYSTEM:
        if not is_valid_timezone(setting):
            raise ValueError(f"不支援的時區：{setting}")
        return DisplayZone(setting, setting, ZoneInfo(setting))
    name = (system_name or _system_timezone_name)()
    if name and is_valid_timezone(name):
        return DisplayZone(SYSTEM, name, ZoneInfo(name))
    return _offset_zone()


_current: DisplayZone | None = None


def set_display_timezone(setting: str) -> DisplayZone:
    global _current
    _current = resolve_timezone(setting)
    return _current


def display_zone() -> DisplayZone:
    global _current
    if _current is None:
        _current = resolve_timezone(SYSTEM)
    return _current


def parse_instant(value: object) -> datetime | None:
    """Return an aware datetime, or None when the value is empty, invalid or naive."""
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.utcoffset() is not None else None


def fanbox_month(value: object) -> str | None:
    """FANBOX month (``YYYY-MM`` in JST) of a time point, or None when it has no explicit offset."""
    parsed = parse_instant(value)
    return parsed.astimezone(FANBOX_TIMEZONE).strftime("%Y-%m") if parsed is not None else None


def _fallback(value: object, empty: str) -> str:
    if not value:
        return empty
    if isinstance(value, datetime):
        return f"{value.isoformat()}{UNKNOWN_ZONE_SUFFIX}"
    text = str(value)
    try:
        datetime.fromisoformat(text.strip())
    except ValueError:
        return text
    return f"{text}{UNKNOWN_ZONE_SUFFIX}"


def format_display(value: object, empty: str = "-") -> str:
    """Human display in the display timezone, e.g. 2026年11月03日 00:00."""
    parsed = parse_instant(value)
    if parsed is None:
        return _fallback(value, empty)
    return parsed.astimezone(display_zone().tz).strftime("%Y年%m月%d日 %H:%M")


def isoformat_display(value: object, empty: str = "-", timespec: str = "seconds") -> str:
    """Machine-readable display with the display timezone's actual offset."""
    parsed = parse_instant(value)
    if parsed is None:
        return _fallback(value, empty)
    return parsed.astimezone(display_zone().tz).isoformat(timespec=timespec)
