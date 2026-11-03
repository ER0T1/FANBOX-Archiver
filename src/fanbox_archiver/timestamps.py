"""Shared Asia/Taipei presentation contract for persisted time points.

Taiwan has observed a fixed UTC+08:00 offset without DST since 1979, so a fixed
offset keeps output identical on every host without requiring tzdata on Windows.
Values without an explicit offset are never guessed; callers show them as-is
with an "unknown timezone" marker instead.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

TAIPEI = timezone(timedelta(hours=8), "Asia/Taipei")
UNKNOWN_ZONE_SUFFIX = "（時區未標示）"


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


def format_taipei(value: object, empty: str = "-") -> str:
    """Human display, e.g. 2026年11月03日 00:00."""
    parsed = parse_instant(value)
    if parsed is None:
        return _fallback(value, empty)
    return parsed.astimezone(TAIPEI).strftime("%Y年%m月%d日 %H:%M")


def isoformat_taipei(value: object, empty: str = "-", timespec: str = "seconds") -> str:
    """Machine-readable display with an explicit +08:00 offset."""
    parsed = parse_instant(value)
    if parsed is None:
        return _fallback(value, empty)
    return parsed.astimezone(TAIPEI).isoformat(timespec=timespec)
