import json
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Event

import httpx
import pytest
import yaml

from fanbox_archiver.application import BackupJobManager, BackupScheduler
from fanbox_archiver.config import AppConfig, ScheduleConfig, StorageConfig
from fanbox_archiver.database import Database
from fanbox_archiver.timestamps import TAIPEI
from fanbox_archiver.webapp import create_app
from test_jobs import SuccessfulUseCase


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def taipei(*args: int) -> datetime:
    return datetime(*args, tzinfo=TAIPEI)


def scheduled(tmp_path: Path, use_case=SuccessfulUseCase, **schedule):
    config = AppConfig(
        storage=StorageConfig(output_dir=tmp_path / "out", database=tmp_path / "out" / "backup.db"),
        schedule=ScheduleConfig(enabled=True, start_date=date(2026, 11, 1), time="03:00", **schedule),
    )
    manager = BackupJobManager(config, use_case_factory=use_case)
    clock = Clock(taipei(2026, 11, 1, 12))
    scheduler = BackupScheduler(lambda: config, lambda: manager, Database(config.storage.database), clock=clock)
    return config, manager, clock, scheduler


def test_enabling_never_fires_for_the_past_then_runs_on_time_once(tmp_path: Path):
    config, manager, clock, scheduler = scheduled(tmp_path, creators=["alice"])
    try:
        assert scheduler.tick() is None  # today's 03:00 passed before the schedule existed
        clock.value = taipei(2026, 11, 2, 2, 59)
        assert scheduler.tick() is None
        clock.value = taipei(2026, 11, 2, 3, 0)
        assert scheduler.tick() == "submitted"
        assert scheduler.tick() is None  # the same occurrence never runs twice
        state = scheduler.status()
        job = manager.wait(state["last_job"]["job_id"])
        assert job["status"] == "completed"
        assert job["request"]["trigger"] == "schedule"
        assert job["request"]["dry_run"] is False
        assert list(job["request"]["creators"]) == ["alice"]
        assert state["note"] is None
        assert state["next_run_at"] == taipei(2026, 11, 3, 3).isoformat()
        assert not {"cookie", "password", "token"} & set(json.dumps(job["request"]).casefold().split('"'))
    finally:
        manager.close()


def test_missed_occurrences_collapse_into_one_catch_up(tmp_path: Path):
    _, manager, clock, scheduler = scheduled(tmp_path)
    try:
        scheduler.tick()
        clock.value = taipei(2026, 11, 5, 12)  # app was closed for four 03:00 runs
        assert scheduler.tick() == "submitted"
        assert "錯過 4 次排程，已補跑最近一次" in scheduler.status()["note"]
        assert scheduler.tick() is None
        manager.wait(scheduler.status()["last_job"]["job_id"])
        assert manager.page(kind="backup")["total"] == 1
    finally:
        manager.close()


def test_busy_occurrence_is_deferred_until_the_running_job_ends(tmp_path: Path):
    started, release = Event(), Event()

    class Blocking(SuccessfulUseCase):
        def run(self, request):
            started.set()
            release.wait(5)
            return super().run(request)

    _, manager, clock, scheduler = scheduled(tmp_path, use_case=Blocking)
    try:
        scheduler.tick()
        manual = manager.submit(scheduler._request(scheduler.get_config()))
        assert started.wait(2)
        clock.value = taipei(2026, 11, 2, 3, 0)
        assert scheduler.tick() == "deferred"
        assert scheduler.tick() == "deferred"
        assert "將於該工作結束後執行" in scheduler.status()["note"]
        release.set()
        manager.wait(manual["job_id"])
        clock.value = taipei(2026, 11, 2, 3, 20)
        assert scheduler.tick() == "submitted"
        assert "曾延後，已於可以執行時補跑" in scheduler.status()["note"]
        manager.wait(scheduler.status()["last_job"]["job_id"])
        assert manager.page(kind="backup")["total"] == 2
    finally:
        release.set()
        manager.close()


def test_disabled_reset_and_run_now_leave_the_schedule_alone(tmp_path: Path):
    config, manager, clock, scheduler = scheduled(tmp_path)
    try:
        scheduler.tick()
        job = scheduler.run_now()
        manager.wait(job["job_id"])
        clock.value = taipei(2026, 11, 2, 4)
        scheduler.reset()  # e.g. the schedule was edited at 04:00
        assert scheduler.tick() is None
        config.schedule.enabled = False
        clock.value = taipei(2026, 11, 3, 4)
        assert scheduler.tick() is None
        assert scheduler.status()["next_run_at"] is None
    finally:
        manager.close()


@pytest.mark.anyio
async def test_schedule_api_saves_previews_and_validates(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config = AppConfig(storage=StorageConfig(output_dir=tmp_path / "out", database=tmp_path / "out" / "backup.db"))
    app = create_app(config, config_path=config_path)
    token = {"X-Fanbox-Token": app.state.session_token}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        assert (await client.get("/api/schedule")).json()["enabled"] is False
        preview = (await client.post("/api/schedule/preview", headers=token, json={
            "frequency": "weekly", "interval": 2, "weekday": 2, "time": "21:05",
        })).json()
        assert preview["summary"] == "每 2 週的週三 21:05（Asia/Taipei）"
        assert len(preview["next_runs"]) == 3 and all(item.endswith("+08:00") for item in preview["next_runs"])
        assert (await client.post("/api/schedule/preview", json={"time": "21:05"})).status_code == 403
        assert (await client.post("/api/schedule/preview", headers=token, json={"time": "25:00"})).status_code == 422

        saved = await client.patch("/api/config", headers=token, json={"schedule": {
            "enabled": True, "frequency": "monthly", "month_day": 31, "time": "02:30",
            "creators": ["https://www.fanbox.cc/@alice", "alice"],
        }})
        assert saved.status_code == 200
        schedule = saved.json()["editable"]["schedule"]
        assert schedule["creators"] == ["alice"]
        assert schedule["start_date"] == datetime.now(TAIPEI).date().isoformat()
        on_disk = yaml.safe_load(config_path.read_text(encoding="utf-8"))["schedule"]
        assert on_disk["enabled"] is True and "timezone" not in on_disk
        status = (await client.get("/api/schedule")).json()
        assert status["summary"].startswith("每月 31 日 02:30")
        assert status["next_run_at"].endswith("+08:00")
        bad = await client.patch("/api/config", headers=token, json={"schedule": {"time": "7pm"}})
        assert bad.status_code == 422
        assert (await client.post("/api/schedule/run")).status_code == 403
    app.state.jobs.close()


def test_restarted_app_keeps_schedule_and_state(tmp_path: Path):
    config, manager, clock, scheduler = scheduled(tmp_path)
    try:
        scheduler.tick()
        clock.value = taipei(2026, 11, 2, 3)
        scheduler.tick()
        manager.wait(scheduler.status()["last_job"]["job_id"])
    finally:
        manager.close()
    restarted = BackupJobManager(config, use_case_factory=SuccessfulUseCase)
    try:
        again = BackupScheduler(lambda: config, lambda: restarted, Database(config.storage.database),
                                clock=Clock(taipei(2026, 11, 2, 9)))
        assert again.tick() is None  # already handled before the restart
        status = again.status()
        assert status["last_due_at"] == taipei(2026, 11, 2, 3).isoformat()
        assert status["last_job"]["status"] == "completed"
        assert status["next_run_at"] == (taipei(2026, 11, 2, 3) + timedelta(days=1)).isoformat()
    finally:
        restarted.close()


@pytest.mark.anyio
async def test_only_a_real_server_runs_the_background_scheduler(tmp_path: Path):
    config = AppConfig(storage=StorageConfig(output_dir=tmp_path / "out", database=tmp_path / "out" / "backup.db"))
    for run_scheduler in (False, True):
        app = create_app(config, run_scheduler=run_scheduler)
        async with app.router.lifespan_context(app):
            assert (app.state.scheduler._thread is not None) is run_scheduler
        assert app.state.scheduler._thread is None
        app.state.jobs.close()
