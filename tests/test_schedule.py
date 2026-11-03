from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from fanbox_archiver.config import ScheduleConfig
from fanbox_archiver.schedule import count_between, describe, latest_due, next_run, upcoming
from fanbox_archiver.timestamps import TAIPEI


def taipei(*args: int) -> datetime:
    return datetime(*args, tzinfo=TAIPEI)


def runs(schedule: ScheduleConfig, after: datetime, count: int) -> list[str]:
    return [item.strftime("%Y-%m-%d %H:%M") for item in upcoming(schedule, after, count)]


def test_daily_and_every_n_days_cross_month_end_from_their_start_date():
    daily = ScheduleConfig(frequency="daily", time="03:00", start_date=date(2026, 1, 30))
    assert runs(daily, taipei(2026, 1, 30, 4), 3) == ["2026-01-31 03:00", "2026-02-01 03:00", "2026-02-02 03:00"]
    every3 = ScheduleConfig(frequency="daily", interval=3, time="23:30", start_date=date(2026, 1, 28))
    assert runs(every3, taipei(2026, 1, 1), 3) == ["2026-01-28 23:30", "2026-01-31 23:30", "2026-02-03 23:30"]
    assert latest_due(every3, taipei(2026, 2, 3, 23, 29)) == taipei(2026, 1, 31, 23, 30)
    assert latest_due(every3, taipei(2026, 1, 28, 23, 29)) is None


def test_weekly_and_every_n_weeks_anchor_on_the_start_week():
    wednesday = ScheduleConfig(frequency="weekly", weekday=2, time="08:15", start_date=date(2026, 11, 5))
    # Start is a Thursday, so the first Wednesday is the following week.
    assert runs(wednesday, taipei(2026, 11, 5), 2) == ["2026-11-11 08:15", "2026-11-18 08:15"]
    fortnight = ScheduleConfig(frequency="weekly", interval=2, weekday=0, time="03:00", start_date=date(2026, 12, 21))
    assert runs(fortnight, taipei(2026, 12, 21), 3) == ["2026-12-21 03:00", "2027-01-04 03:00", "2027-01-18 03:00"]
    assert latest_due(fortnight, taipei(2027, 1, 17)) == taipei(2027, 1, 4, 3)


@pytest.mark.parametrize(("month_day", "expected"), [
    (31, ["2027-01-31 03:00", "2027-02-28 03:00", "2027-03-31 03:00", "2027-04-30 03:00"]),
    (29, ["2027-01-29 03:00", "2027-02-28 03:00", "2027-03-29 03:00", "2027-04-29 03:00"]),
    (15, ["2027-01-15 03:00", "2027-02-15 03:00", "2027-03-15 03:00", "2027-04-15 03:00"]),
])
def test_monthly_uses_last_day_for_short_months(month_day, expected):
    schedule = ScheduleConfig(frequency="monthly", month_day=month_day, time="03:00", start_date=date(2027, 1, 1))
    assert runs(schedule, taipei(2027, 1, 1), 4) == expected


def test_monthly_leap_year_february_and_year_rollover():
    schedule = ScheduleConfig(frequency="monthly", month_day=30, time="22:00", start_date=date(2027, 12, 1))
    assert runs(schedule, taipei(2027, 12, 31), 3) == ["2028-01-30 22:00", "2028-02-29 22:00", "2028-03-30 22:00"]
    assert latest_due(schedule, taipei(2028, 3, 1)) == taipei(2028, 2, 29, 22)


def test_taipei_midnight_boundary_and_host_independent_utc_inputs():
    schedule = ScheduleConfig(frequency="daily", time="00:00", start_date=date(2026, 11, 1))
    # 2026-11-02T16:00Z is exactly 2026-11-03 00:00 in Taipei.
    assert latest_due(schedule, datetime(2026, 11, 2, 16, tzinfo=UTC)) == taipei(2026, 11, 3)
    assert latest_due(schedule, datetime(2026, 11, 2, 15, 59, tzinfo=UTC)) == taipei(2026, 11, 2)
    eastern = timezone(timedelta(hours=-5))
    assert next_run(schedule, datetime(2026, 11, 2, 10, 59, tzinfo=eastern)) == taipei(2026, 11, 3)


def test_missed_occurrences_are_counted_for_the_single_catch_up():
    schedule = ScheduleConfig(frequency="daily", time="03:00", start_date=date(2026, 11, 1))
    assert count_between(schedule, taipei(2026, 11, 1, 4), taipei(2026, 11, 5, 12)) == 4
    assert count_between(schedule, taipei(2026, 11, 1, 4), taipei(2026, 11, 2, 2)) == 0


def test_description_and_time_validation():
    assert describe(ScheduleConfig(frequency="daily")) == "每天 00:00（Asia/Taipei）"
    assert describe(ScheduleConfig(frequency="weekly", interval=2, weekday=2, time="21:05")) == "每 2 週的週三 21:05（Asia/Taipei）"
    assert describe(ScheduleConfig(frequency="monthly", month_day=31)).endswith("該月沒有這一天時於月底執行")
    for bad in ("24:00", "3:00", "03:60", "noon"):
        with pytest.raises(ValueError):
            ScheduleConfig(time=bad)
