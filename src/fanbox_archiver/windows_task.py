"""Windows Task Scheduler integration for background scheduled backups.

Two per-user tasks live in the ``FANBOX Archiver`` folder:

* ``Scheduled Backup`` checks every 15 minutes, aligned to the schedule time, and
  at sign-in. It never wakes the PC, so a missed run is retried 15 minutes later.
* ``Scheduled Backup Wake`` exists only with the "wake" power option: a one-shot
  trigger at the next occurrence with WakeToRun, re-pointed after every check.

Both run the desktop app with ``--scheduled-backup``; it starts the sidecar's
``schedule-run`` hidden, so no window appears. The occurrence arithmetic stays in
``schedule.py``; the tasks only decide when to look.
"""

from __future__ import annotations

import getpass
import os
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from xml.sax.saxutils import escape

from .config import AppConfig, ScheduleConfig
from .i18n import Text, error_text, resolve_locale, system_locales, translate
from .schedule import next_run
from .timestamps import display_zone

TASK_FOLDER = "FANBOX Archiver"
CHECK_TASK = rf"{TASK_FOLDER}\Scheduled Backup"
WAKE_TASK = rf"{TASK_FOLDER}\Scheduled Backup Wake"
CHECK_INTERVAL_MINUTES = 15
DESKTOP_EXE_ENV = "FANBOX_ARCHIVER_DESKTOP_EXE"

Runner = Callable[[list[str]], subprocess.CompletedProcess]


def _run(arguments: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        arguments, capture_output=True, text=True, encoding="mbcs" if os.name == "nt" else "utf-8",
        errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
    )


def current_user() -> str:
    domain = os.environ.get("USERDOMAIN")
    user = getpass.getuser()
    return f"{domain}\\{user}" if domain else user


def task_xml(
    *, command: Path, arguments: str, start: datetime, user: str, schedule: ScheduleConfig,
    repeat: bool, wake: bool, description: str,
) -> str:
    """Task Scheduler 1.3 XML; ``start`` keeps its UTC offset so host timezone never matters."""
    repetition = (
        f"<Repetition><Interval>PT{CHECK_INTERVAL_MINUTES}M</Interval>"
        "<StopAtDurationEnd>false</StopAtDurationEnd></Repetition>" if repeat else ""
    )
    logon = (
        f"<LogonTrigger><Enabled>true</Enabled><UserId>{escape(user)}</UserId><Delay>PT1M</Delay></LogonTrigger>"
        if repeat else ""
    )
    ac_only = schedule.power == "no_wake_ac_only"
    flag = lambda value: "true" if value else "false"  # noqa: E731
    return (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
        f"<RegistrationInfo><Description>{escape(description)}</Description></RegistrationInfo>"
        "<Triggers>"
        f"<TimeTrigger>{repetition}<StartBoundary>{start.isoformat(timespec='seconds')}</StartBoundary>"
        "<Enabled>true</Enabled></TimeTrigger>"
        f"{logon}"
        "</Triggers>"
        f'<Principals><Principal id="Author"><UserId>{escape(user)}</UserId>'
        "<LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>"
        "<Settings>"
        "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>"
        f"<DisallowStartIfOnBatteries>{flag(ac_only)}</DisallowStartIfOnBatteries>"
        "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>"
        "<AllowHardTerminate>true</AllowHardTerminate>"
        "<StartWhenAvailable>true</StartWhenAvailable>"
        "<RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>"
        "<IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>"
        "<AllowStartOnDemand>true</AllowStartOnDemand><Enabled>true</Enabled><Hidden>false</Hidden>"
        "<RunOnlyIfIdle>false</RunOnlyIfIdle>"
        f"<WakeToRun>{flag(wake)}</WakeToRun>"
        "<ExecutionTimeLimit>PT12H</ExecutionTimeLimit><Priority>7</Priority>"
        "</Settings>"
        '<Actions Context="Author"><Exec>'
        f"<Command>{escape(str(command))}</Command><Arguments>{escape(arguments)}</Arguments>"
        "</Exec></Actions></Task>"
    )


def check_start(schedule: ScheduleConfig, now: datetime) -> datetime:
    """Yesterday at the schedule time in the display timezone, with that zone's offset,
    so 15-minute checks land on the schedule time; the app re-syncs on every start."""
    zone = display_zone().tz
    hour, minute = (int(part) for part in schedule.time.split(":"))
    day = now.astimezone(zone).date() - timedelta(days=1)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)


class TaskScheduler:
    def __init__(self, runner: Runner = _run, *, check_task: str = CHECK_TASK, wake_task: str = WAKE_TASK) -> None:
        self.runner = runner
        self.check_task = check_task
        self.wake_task = wake_task

    def create(self, name: str, xml: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "task.xml"
            path.write_text(xml, encoding="utf-16")
            result = self.runner(["schtasks", "/Create", "/TN", name, "/XML", str(path), "/F"])
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "").strip() or Text("schedule.schtasks_failed"))

    def delete(self, name: str) -> None:
        if self.exists(name):
            result = self.runner(["schtasks", "/Delete", "/TN", name, "/F"])
            if result.returncode != 0:
                raise RuntimeError((result.stderr or result.stdout or "").strip() or Text("schedule.schtasks_failed"))

    def exists(self, name: str) -> bool:
        return self.runner(["schtasks", "/Query", "/TN", name]).returncode == 0

    def query_xml(self, name: str) -> str | None:
        result = self.runner(["schtasks", "/Query", "/TN", name, "/XML"])
        return result.stdout if result.returncode == 0 else None


def _task_text(config: AppConfig, key: str) -> str:
    # Shown in Windows Task Scheduler, outside any browser: the configured language, else the system's.
    return translate(key, resolve_locale(config.display.language, system_locales()))


def refresh_wake_task(
    config: AppConfig, config_path: Path, desktop_exe: str | None, *,
    now: datetime, tasks: TaskScheduler | None = None, user: str | None = None,
) -> None:
    """After a background check, point the one-shot wake trigger at the next occurrence."""
    if os.name != "nt" or not desktop_exe or config.schedule.power != "wake" or not config.schedule.enabled:
        return
    tasks = tasks or TaskScheduler()
    tasks.create(tasks.wake_task, task_xml(
        command=Path(desktop_exe), arguments=f'--scheduled-backup --config "{Path(config_path).resolve()}"',
        start=next_run(config.schedule, now), user=user or current_user(), schedule=config.schedule,
        repeat=False, wake=True, description=_task_text(config, "schedule.task_wake"),
    ))


def sync_background_schedule(
    config: AppConfig, config_path: Path | None, desktop_exe: str | None, *,
    now: datetime, tasks: TaskScheduler | None = None, user: str | None = None,
) -> dict[str, Any]:
    """Make the Windows tasks match the saved schedule; report the outcome for the UI."""
    if os.name != "nt" or not desktop_exe or config_path is None:
        return {"state": "unavailable", "message": Text("schedule.background_unavailable")}
    tasks = tasks or TaskScheduler()
    schedule = config.schedule
    try:
        if not schedule.enabled:
            tasks.delete(tasks.wake_task)
            tasks.delete(tasks.check_task)
            return {"state": "removed", "message": Text("schedule.background_removed")}
        user = user or current_user()
        command = Path(desktop_exe)
        arguments = f'--scheduled-backup --config "{Path(config_path).resolve()}"'
        tasks.create(tasks.check_task, task_xml(
            command=command, arguments=arguments, start=check_start(schedule, now), user=user,
            schedule=schedule, repeat=True, wake=False,
            description=_task_text(config, "schedule.task_check"),
        ))
        if schedule.power == "wake":
            tasks.create(tasks.wake_task, task_xml(
                command=command, arguments=arguments, start=next_run(schedule, now), user=user,
                schedule=schedule, repeat=False, wake=True,
                description=_task_text(config, "schedule.task_wake"),
            ))
        else:
            tasks.delete(tasks.wake_task)
    except (OSError, RuntimeError) as exc:
        return {"state": "error", "message": Text("schedule.background_failed", error=error_text(exc))}
    registered = "schedule.background_registered_wake" if schedule.power == "wake" else "schedule.background_registered"
    return {"state": "registered", "message": Text(registered)}
