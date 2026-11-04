"""Pure occurrence arithmetic for the automatic backup schedule.

Every occurrence is a wall-clock time in the display timezone (the global
timezone setting). Monthly schedules on a day the month does not have (29–31)
run on that month's last day. DST transitions get no special handling.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta, tzinfo

from .config import ScheduleConfig
from .i18n import Text
from .timestamps import display_zone

# Occurrences are at most a month apart, so a few hundred steps cover any search.
_MAX_STEPS = 500


def _clock(schedule: ScheduleConfig) -> time:
    hour, minute = (int(part) for part in schedule.time.split(":"))
    return time(hour, minute)


def _zone(zone: tzinfo | None) -> tzinfo:
    return zone or display_zone().tz


def _start(schedule: ScheduleConfig, reference: datetime, zone: tzinfo) -> date:
    return schedule.start_date or reference.astimezone(zone).date()


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


def next_run(schedule: ScheduleConfig, after: datetime, zone: tzinfo | None = None) -> datetime:
    """The first occurrence strictly after ``after`` (an aware datetime)."""
    zone = _zone(zone)
    start = _start(schedule, after, zone)
    clock = _clock(schedule)
    day = after.astimezone(zone).date()
    for _ in range(_MAX_STEPS):
        day = _first_day_on_or_after(schedule, start, day)
        occurrence = datetime.combine(day, clock, zone)
        if occurrence > after:
            return occurrence
        day += timedelta(days=1)
    raise RuntimeError(Text("schedule.next_run_failed"))


def latest_due(schedule: ScheduleConfig, now: datetime, zone: tzinfo | None = None) -> datetime | None:
    """The most recent occurrence at or before ``now``, or None before the first one."""
    zone = _zone(zone)
    start = _start(schedule, now, zone)
    clock = _clock(schedule)
    day = now.astimezone(zone).date()
    for _ in range(_MAX_STEPS):
        found = _last_day_on_or_before(schedule, start, day)
        if found is None:
            return None
        occurrence = datetime.combine(found, clock, zone)
        if occurrence <= now:
            return occurrence
        day = found - timedelta(days=1)
    return None


def upcoming(
    schedule: ScheduleConfig, after: datetime, count: int = 3, zone: tzinfo | None = None,
) -> list[datetime]:
    runs: list[datetime] = []
    cursor = after
    for _ in range(count):
        cursor = next_run(schedule, cursor, zone)
        runs.append(cursor)
    return runs


def count_between(
    schedule: ScheduleConfig, after: datetime, until: datetime, limit: int = 100, zone: tzinfo | None = None,
) -> int:
    """Occurrences in (after, until], capped at ``limit``."""
    count = 0
    cursor = after
    while count < limit:
        cursor = next_run(schedule, cursor, zone)
        if cursor > until:
            break
        count += 1
    return count


def describe(schedule: ScheduleConfig, zone_name: str | None = None) -> Text:
    """Human-readable summary, e.g. 每 2 週的週三 03:00（Asia/Taipei）."""
    at = {"time": schedule.time, "zone": zone_name or display_zone().name}
    if schedule.frequency == "daily":
        if schedule.interval == 1:
            return Text("schedule.summary_daily", **at)
        return Text("schedule.summary_every_days", count=schedule.interval, **at)
    if schedule.frequency == "weekly":
        weekday = Text(f"schedule.weekday_{schedule.weekday}")
        if schedule.interval == 1:
            return Text("schedule.summary_weekly", weekday=weekday, **at)
        return Text("schedule.summary_every_weeks", count=schedule.interval, weekday=weekday, **at)
    end = "schedule.summary_monthly_end" if schedule.month_day > 28 else "schedule.summary_monthly"
    return Text(end, day=schedule.month_day, **at)
