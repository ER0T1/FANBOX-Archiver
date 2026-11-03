"""Pure occurrence arithmetic for the automatic backup schedule.

Every occurrence is a wall-clock time in Asia/Taipei, which has no DST, so each
day has exactly one instant for a given HH:MM. Monthly schedules on a day the
month does not have (29–31) run on that month's last day.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta

from .config import ScheduleConfig
from .timestamps import TAIPEI

_WEEKDAYS = ("一", "二", "三", "四", "五", "六", "日")
# Occurrences are at most a month apart, so a few hundred steps cover any search.
_MAX_STEPS = 500


def _clock(schedule: ScheduleConfig) -> time:
    hour, minute = (int(part) for part in schedule.time.split(":"))
    return time(hour, minute)


def _start(schedule: ScheduleConfig, reference: datetime) -> date:
    return schedule.start_date or reference.astimezone(TAIPEI).date()


def _month_day(year: int, month: int, wanted: int) -> date:
    return date(year, month, min(wanted, monthrange(year, month)[1]))


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _first_day_on_or_after(schedule: ScheduleConfig, start: date, day: date) -> date:
    day = max(day, start)
    if schedule.frequency == "daily":
        offset = (day - start).days
        return start + timedelta(days=-(-offset // schedule.interval) * schedule.interval)
    if schedule.frequency == "weekly":
        anchor = start - timedelta(days=start.weekday())
        weeks = (day - anchor).days // 7
        weeks = -(-weeks // schedule.interval) * schedule.interval
        while True:
            candidate = anchor + timedelta(weeks=weeks, days=schedule.weekday)
            if candidate >= day:
                return candidate
            weeks += schedule.interval
    candidate = _month_day(day.year, day.month, schedule.month_day)
    if candidate < day:
        year, month = _add_months(day.year, day.month, 1)
        candidate = _month_day(year, month, schedule.month_day)
    return candidate


def _last_day_on_or_before(schedule: ScheduleConfig, start: date, day: date) -> date | None:
    if day < start:
        return None
    if schedule.frequency == "daily":
        offset = (day - start).days
        return start + timedelta(days=offset // schedule.interval * schedule.interval)
    if schedule.frequency == "weekly":
        anchor = start - timedelta(days=start.weekday())
        weeks = (day - anchor).days // 7 // schedule.interval * schedule.interval
        while weeks >= 0:
            candidate = anchor + timedelta(weeks=weeks, days=schedule.weekday)
            if start <= candidate <= day:
                return candidate
            weeks -= schedule.interval
        return None
    candidate = _month_day(day.year, day.month, schedule.month_day)
    if candidate > day:
        year, month = _add_months(day.year, day.month, -1)
        candidate = _month_day(year, month, schedule.month_day)
    return candidate if candidate >= start else None


def next_run(schedule: ScheduleConfig, after: datetime) -> datetime:
    """The first occurrence strictly after ``after`` (an aware datetime)."""
    start = _start(schedule, after)
    clock = _clock(schedule)
    day = after.astimezone(TAIPEI).date()
    for _ in range(_MAX_STEPS):
        day = _first_day_on_or_after(schedule, start, day)
        occurrence = datetime.combine(day, clock, TAIPEI)
        if occurrence > after:
            return occurrence
        day += timedelta(days=1)
    raise RuntimeError("排程無法計算下一次執行時間")


def latest_due(schedule: ScheduleConfig, now: datetime) -> datetime | None:
    """The most recent occurrence at or before ``now``, or None before the first one."""
    start = _start(schedule, now)
    clock = _clock(schedule)
    day = now.astimezone(TAIPEI).date()
    for _ in range(_MAX_STEPS):
        found = _last_day_on_or_before(schedule, start, day)
        if found is None:
            return None
        occurrence = datetime.combine(found, clock, TAIPEI)
        if occurrence <= now:
            return occurrence
        day = found - timedelta(days=1)
    return None


def upcoming(schedule: ScheduleConfig, after: datetime, count: int = 3) -> list[datetime]:
    runs: list[datetime] = []
    cursor = after
    for _ in range(count):
        cursor = next_run(schedule, cursor)
        runs.append(cursor)
    return runs


def count_between(schedule: ScheduleConfig, after: datetime, until: datetime, limit: int = 100) -> int:
    """Occurrences in (after, until], capped at ``limit``."""
    count = 0
    cursor = after
    while count < limit:
        cursor = next_run(schedule, cursor)
        if cursor > until:
            break
        count += 1
    return count


def describe(schedule: ScheduleConfig) -> str:
    """Human-readable summary, e.g. 每 2 週的週三 03:00（Asia/Taipei）."""
    at = f"{schedule.time}（Asia/Taipei）"
    if schedule.frequency == "daily":
        period = "每天" if schedule.interval == 1 else f"每 {schedule.interval} 天"
        return f"{period} {at}"
    if schedule.frequency == "weekly":
        day = f"週{_WEEKDAYS[schedule.weekday]}"
        period = f"每{day}" if schedule.interval == 1 else f"每 {schedule.interval} 週的{day}"
        return f"{period} {at}"
    short = "；該月沒有這一天時於月底執行" if schedule.month_day > 28 else ""
    return f"每月 {schedule.month_day} 日 {at}{short}"
