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

from .i18n import Text, datetime_params

SYSTEM = "system"
DEVELOPMENT_TIMEZONE = "Asia/Taipei"
TAIPEI = ZoneInfo(DEVELOPMENT_TIMEZONE)
# FANBOX bills and changes Fan Cards on Japanese calendar months; this is data semantics,
# so it never follows the display timezone.
FANBOX_TIMEZONE = ZoneInfo("Asia/Tokyo")
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
    return DisplayZone(SYSTEM, name, zone, Text("settings.timezone_offset_notice"))


def resolve_timezone(setting: str, *, system_name: Callable[[], str | None] | None = None) -> DisplayZone:
    if setting != SYSTEM:
        if not is_valid_timezone(setting):
            raise ValueError(Text("config.timezone_unsupported", value=setting))
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


def unrecorded_zone(value: object, empty: str) -> str:
    """Show a value without an explicit offset as-is, marked "time zone not recorded" (``Text``)."""
    if not value:
        return empty
    text = value.isoformat() if isinstance(value, datetime) else str(value)
    try:
        datetime.fromisoformat(text.strip())
    except ValueError:
        return text
    return Text("common.timezone_unknown", value=text)


def format_display(value: object, empty: str = "-") -> str:
    """Human display in the display timezone, e.g. 2026年11月03日 00:00 or November 3rd, 2026 00:00.

    The result is :class:`Text`: the base-language string that each boundary (web server, CLI)
    shows in its own language and date format.
    """
    parsed = parse_instant(value)
    if parsed is None:
        return unrecorded_zone(value, empty)
    local = parsed.astimezone(display_zone().tz)
    return Text("common.datetime", **datetime_params(local.year, local.month, local.day, local.hour, local.minute))


def isoformat_display(value: object, empty: str = "-", timespec: str = "seconds") -> str:
    """Machine-readable display with the display timezone's actual offset.

    Always a plain string in the base language: it is written into archive files (Markdown
    front matter), which are never translated. The CLI marks legacy values itself.
    """
    parsed = parse_instant(value)
    if parsed is None:
        shown = unrecorded_zone(value, empty)
        return str(shown) if isinstance(shown, str) else shown
    return parsed.astimezone(display_zone().tz).isoformat(timespec=timespec)
