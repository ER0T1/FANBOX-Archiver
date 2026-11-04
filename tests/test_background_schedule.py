import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import fanbox_archiver.cli as cli
import fanbox_archiver.webapp as webapp
from fanbox_archiver.application import BackupJobManager, BackupRequest, BackupScheduler
from fanbox_archiver.archive_lock import ArchiveLock
from fanbox_archiver.config import AppConfig, ScheduleConfig, StorageConfig
from fanbox_archiver.database import Database
from fanbox_archiver.timestamps import TAIPEI
from fanbox_archiver.windows_task import (
    TaskScheduler, check_start, sync_background_schedule, task_xml,
)
from test_jobs import SuccessfulUseCase

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
runner = CliRunner()


def text(root: ET.Element, path: str) -> str | None:
    node = root.find(path, NS)
    return node.text if node is not None else None


def archive(tmp_path: Path, **schedule) -> AppConfig:
    return AppConfig(
        storage=StorageConfig(output_dir=tmp_path / "out", database=tmp_path / "out" / "backup.db"),
        schedule=ScheduleConfig(enabled=True, start_date=date(2026, 11, 1), **schedule),
    )


class FakeSchtasks:
    def __init__(self, fail: bool = False) -> None:
        self.tasks: dict[str, str] = {}
        self.fail = fail

    def __call__(self, arguments: list[str]) -> subprocess.CompletedProcess:
        verb, name = arguments[1], arguments[3]
        if self.fail and verb == "/Create":
            return subprocess.CompletedProcess(arguments, 1, "", "ERROR: Access is denied.")
        if verb == "/Create":
            self.tasks[name] = Path(arguments[5]).read_text(encoding="utf-16")
            return subprocess.CompletedProcess(arguments, 0, "SUCCESS", "")
        if verb == "/Delete":
            self.tasks.pop(name, None)
            return subprocess.CompletedProcess(arguments, 0, "SUCCESS", "")
        return subprocess.CompletedProcess(arguments, 0 if name in self.tasks else 1, "", "")


@pytest.mark.parametrize(("power", "wake", "ac_only"), [
    ("no_wake_battery_ok", "false", "false"), ("no_wake_ac_only", "false", "true"), ("wake", "false", "false"),
])
def test_check_task_runs_every_15_minutes_from_the_taipei_schedule_time(power, wake, ac_only):
    schedule = ScheduleConfig(time="00:00", power=power)
    start = check_start(schedule, datetime(2026, 11, 3, 1, tzinfo=UTC))
    assert start.isoformat() == "2026-11-02T00:00:00+08:00"
    xml = task_xml(command=Path(r"C:\Program Files\FANBOX Archiver\app.exe"),
                   arguments='--scheduled-backup --config "C:\\A & B\\config.yaml"', start=start,
                   user=r"PC\user", schedule=schedule, repeat=True, wake=False, description="d")
    root = ET.fromstring(xml.split("\n", 1)[1])
    assert text(root, "t:Triggers/t:TimeTrigger/t:StartBoundary") == "2026-11-02T00:00:00+08:00"
    assert text(root, "t:Triggers/t:TimeTrigger/t:Repetition/t:Interval") == "PT15M"
    assert text(root, "t:Triggers/t:LogonTrigger/t:UserId") == r"PC\user"
    assert text(root, "t:Settings/t:WakeToRun") == wake  # the 15-minute check never wakes the PC
    assert text(root, "t:Settings/t:DisallowStartIfOnBatteries") == ac_only
    assert text(root, "t:Settings/t:StartWhenAvailable") == "true"
    assert text(root, "t:Settings/t:MultipleInstancesPolicy") == "IgnoreNew"
    assert text(root, "t:Actions/t:Exec/t:Arguments") == '--scheduled-backup --config "C:\\A & B\\config.yaml"'
    assert text(root, "t:Principals/t:Principal/t:LogonType") == "InteractiveToken"


def test_wake_task_is_a_one_shot_at_the_next_occurrence():
    schedule = ScheduleConfig(time="21:30", power="wake")
    xml = task_xml(command=Path("app.exe"), arguments="", start=datetime(2026, 11, 3, 21, 30, tzinfo=TAIPEI),
                   user="u", schedule=schedule, repeat=False, wake=True, description="d")
    root = ET.fromstring(xml.split("\n", 1)[1])
    assert root.find("t:Triggers/t:TimeTrigger/t:Repetition", NS) is None
    assert root.find("t:Triggers/t:LogonTrigger", NS) is None
    assert text(root, "t:Settings/t:WakeToRun") == "true"
    assert text(root, "t:Triggers/t:TimeTrigger/t:StartBoundary") == "2026-11-03T21:30:00+08:00"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Task Scheduler only")
def test_sync_creates_updates_and_removes_tasks(tmp_path: Path):
    fake = FakeSchtasks()
    tasks = TaskScheduler(fake, check_task="T\\check", wake_task="T\\wake")
    now = datetime(2026, 11, 3, 4, tzinfo=UTC)
    config, path = archive(tmp_path, power="wake"), tmp_path / "config.yaml"
    result = sync_background_schedule(config, path, r"C:\app.exe", now=now, tasks=tasks, user="u")
    assert result["state"] == "registered" and set(fake.tasks) == {"T\\check", "T\\wake"}
    assert "2026-11-04T00:00:00+08:00" in fake.tasks["T\\wake"]
    assert str(path.resolve()) in fake.tasks["T\\check"]

    config.schedule.power = "no_wake_battery_ok"
    assert sync_background_schedule(config, path, r"C:\app.exe", now=now, tasks=tasks, user="u")["state"] == "registered"
    assert set(fake.tasks) == {"T\\check"}
    config.schedule.enabled = False
    assert sync_background_schedule(config, path, r"C:\app.exe", now=now, tasks=tasks, user="u")["state"] == "removed"
    assert fake.tasks == {}

    assert sync_background_schedule(config, path, None, now=now, tasks=tasks)["state"] == "unavailable"
    config.schedule.enabled = True
    failing = TaskScheduler(FakeSchtasks(fail=True), check_task="T\\check", wake_task="T\\wake")
    error = sync_background_schedule(config, path, r"C:\app.exe", now=now, tasks=failing, user="u")
    assert error["state"] == "error" and "Access is denied" in error["message"]


def test_manager_defers_to_another_process_that_owns_the_archive(tmp_path: Path):
    config = archive(tmp_path)
    database = Database(config.storage.database)
    database.create_web_job("bg", json.dumps({"trigger": "schedule"}), "2026-11-03T00:00:00+00:00",
                            "2026-11-03T00:00:00+00:00", kind="backup")
    database.update_web_job("bg", status="running", updated_at="2026-11-03T00:00:01+00:00",
                            started_at="2026-11-03T00:00:00+00:00", finished_at=None, error=None, result_json=None)
    background = ArchiveLock(config.storage.output_dir)
    assert background.try_acquire()
    manager = BackupJobManager(config, use_case_factory=SuccessfulUseCase,
                               archive_lock=ArchiveLock(config.storage.output_dir))
    try:
        assert manager.has_active() is True
        page = manager.page()
        assert page["active"]["job_id"] == "bg" and page["active"]["external"] is True
        with pytest.raises(RuntimeError, match="背景排程備份執行中"):
            manager.submit(BackupRequest())
        assert manager.get("bg")["status"] == "running"  # never marked interrupted while it runs

        database.update_web_job("bg", status="completed", updated_at="2026-11-03T00:05:00+00:00",
                                started_at="2026-11-03T00:00:00+00:00",
                                finished_at="2026-11-03T00:05:00+00:00", error=None, result_json=None)
        background.release()
        assert manager.has_active() is False
        assert manager.get("bg")["status"] == "completed"
        job = manager.submit(BackupRequest())
        assert manager.wait(job["job_id"])["status"] == "completed"
    finally:
        background.release()
        manager.close()


def test_manager_recovers_stale_running_rows_once_it_owns_the_archive(tmp_path: Path):
    config = archive(tmp_path)
    database = Database(config.storage.database)
    database.create_web_job("stale", "{}", "2026-11-03T00:00:00+00:00", "2026-11-03T00:00:00+00:00", kind="backup")
    database.update_web_job("stale", status="running", updated_at="2026-11-03T00:00:00+00:00",
                            started_at="2026-11-03T00:00:00+00:00", finished_at=None, error=None, result_json=None)
    manager = BackupJobManager(config, use_case_factory=SuccessfulUseCase,
                               archive_lock=ArchiveLock(config.storage.output_dir))
    try:
        assert manager.get("stale")["status"] == "interrupted"
    finally:
        manager.close()


def make_due(config: AppConfig) -> None:
    db = Database(config.storage.database)
    db.set_schedule_state(handled_through=datetime(2026, 11, 1, 12, tzinfo=TAIPEI).isoformat())


def fake_manager(monkeypatch):
    real = BackupJobManager
    monkeypatch.setattr(cli, "BackupJobManager",
                        lambda settings, **kwargs: real(settings, use_case_factory=SuccessfulUseCase, **kwargs))


def test_schedule_run_backs_up_once_when_due_and_skips_otherwise(tmp_path: Path, monkeypatch):
    config = archive(tmp_path)
    monkeypatch.setattr(cli, "load_config", lambda path: config)
    fake_manager(monkeypatch)
    make_due(config)

    assert runner.invoke(cli.app, ["schedule-run"]).exit_code == 0
    jobs = Database(config.storage.database).web_job_page(kind="backup", limit=10)
    assert len(jobs) == 1 and jobs[0]["status"] == "completed"
    assert json.loads(jobs[0]["request_json"])["trigger"] == "schedule"
    assert runner.invoke(cli.app, ["schedule-run"]).exit_code == 0  # nothing new is due
    assert len(Database(config.storage.database).web_job_page(kind="backup", limit=10)) == 1

    holder = ArchiveLock(config.storage.output_dir)
    assert holder.try_acquire()
    try:
        make_due(config)
        assert runner.invoke(cli.app, ["schedule-run"]).exit_code == 0  # the app owns it; skip
        assert len(Database(config.storage.database).web_job_page(kind="backup", limit=10)) == 1
    finally:
        holder.release()

    config.schedule.enabled = False
    assert runner.invoke(cli.app, ["schedule-run"]).exit_code == 0


def test_ac_only_schedule_waits_for_mains_power(tmp_path: Path, monkeypatch):
    config = archive(tmp_path, power="no_wake_ac_only")
    manager = BackupJobManager(config, use_case_factory=SuccessfulUseCase)
    battery = {"on": True}
    monkeypatch.setattr("fanbox_archiver.power.on_battery", lambda: battery["on"])
    scheduler = BackupScheduler(lambda: config, lambda: manager, Database(config.storage.database),
                                clock=lambda: datetime(2026, 11, 2, 0, 5, tzinfo=TAIPEI))
    try:
        make_due(config)
        assert scheduler.tick() == "deferred"
        assert "使用電池中" in scheduler.status()["note"]
        battery["on"] = False
        assert scheduler.tick() == "submitted"
        manager.wait(scheduler.status()["last_job"]["job_id"])
    finally:
        manager.close()


@pytest.mark.anyio
async def test_settings_save_syncs_the_background_task_and_reports_it(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr(webapp, "sync_background_schedule", lambda config, path, exe, now: (
        calls.append((config.schedule.enabled, config.schedule.power, exe))
        or {"state": "registered", "message": "已設定 Windows 背景排程"}))
    monkeypatch.setenv("FANBOX_ARCHIVER_DESKTOP_EXE", r"C:\app.exe")
    config = AppConfig(storage=StorageConfig(output_dir=tmp_path / "out", database=tmp_path / "out" / "backup.db"))
    app = webapp.create_app(config, config_path=tmp_path / "config.yaml")
    token = {"X-Fanbox-Token": app.state.session_token}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        assert (await client.get("/api/schedule")).json()["background"]["state"] == "unavailable"
        saved = await client.patch("/api/config", headers=token, json={"schedule": {"enabled": True, "power": "wake"}})
        assert saved.status_code == 200
        assert calls == [(True, "wake", r"C:\app.exe")]
        assert (await client.get("/api/schedule")).json()["background"]["state"] == "registered"
        await client.patch("/api/config", headers=token, json={"schedule": {"enabled": True, "power": "wake"}})
        assert len(calls) == 1  # unchanged schedule: no task rewrite
        bad = await client.patch("/api/config", headers=token, json={"schedule": {"power": "always"}})
        assert bad.status_code == 422
    app.state.jobs.close()


def test_tokyo_timezone_moves_schedule_and_task_boundary():
    from fanbox_archiver import timestamps
    from fanbox_archiver.schedule import describe, next_run
    from zoneinfo import ZoneInfo

    timestamps.set_display_timezone("Asia/Tokyo")
    schedule = ScheduleConfig(time="00:00", start_date=date(2026, 11, 1))
    # 00:00 in Tokyo is 23:00 the previous day in Taipei.
    assert next_run(schedule, datetime(2026, 11, 2, 14, 30, tzinfo=UTC)) == datetime(2026, 11, 3, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert next_run(schedule, datetime(2026, 11, 2, 14, 30, tzinfo=UTC)).astimezone(TAIPEI).hour == 23
    assert describe(schedule) == "每天 00:00（Asia/Tokyo）"
    assert check_start(schedule, datetime(2026, 11, 3, 1, tzinfo=UTC)).isoformat() == "2026-11-02T00:00:00+09:00"


@pytest.mark.anyio
async def test_saving_a_timezone_applies_everywhere_and_restarts_schedule_counting(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr(webapp, "sync_background_schedule", lambda *args, **kwargs: (
        calls.append(1) or {"state": "unavailable", "message": "x"}))
    config = AppConfig(storage=StorageConfig(output_dir=tmp_path / "out", database=tmp_path / "out" / "backup.db"),
                       schedule=ScheduleConfig(enabled=True, start_date=date(2026, 11, 1)))
    app = webapp.create_app(config, config_path=tmp_path / "config.yaml")
    token = {"X-Fanbox-Token": app.state.session_token}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1",
                                 headers={"Accept-Language": "zh-TW"}) as client:
        current = (await client.get("/api/config")).json()
        assert current["display"] == {"setting": "system", "timezone": "Asia/Taipei", "notice": None,
                                      "system_timezone": "Asia/Taipei"}
        assert "Asia/Tokyo" in current["timezones"]["all"] and current["timezones"]["common"][0] == "Asia/Taipei"
        assert 'content="Asia/Taipei"' in (await client.get("/")).text

        saved = await client.patch("/api/config", headers=token, json={"display": {"timezone": "Asia/Tokyo"}})
        assert saved.status_code == 200 and saved.json()["display"]["timezone"] == "Asia/Tokyo"
        assert 'content="Asia/Tokyo"' in (await client.get("/")).text
        status = (await client.get("/api/schedule")).json()
        assert status["timezone"] == "Asia/Tokyo" and status["summary"].endswith("（Asia/Tokyo）")
        assert status["next_run_at"].endswith("+09:00")
        assert calls == [1]  # the Windows task follows the new zone
        assert Database(config.storage.database).schedule_state()["handled_through"] is not None

        bad = await client.patch("/api/config", headers=token, json={"display": {"timezone": "Mars/Olympus"}})
        assert bad.status_code == 422
        assert (await client.get("/api/config")).json()["display"]["timezone"] == "Asia/Tokyo"
    app.state.jobs.close()
