import json
import time
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from fanbox_archiver.application import BackupCancelled, BackupEvent, BackupJobManager, BackupRequest
from fanbox_archiver.config import AppConfig, StorageConfig
from fanbox_archiver.database import Database


class SuccessfulUseCase:
    def __init__(self, config, *, sink, cancellation):
        self.sink = sink

    def run(self, request):
        self.sink.emit(BackupEvent("plan_ready", {"new": 1}))
        self.sink.emit(BackupEvent("job_finished", {"success": 1}))
        return SimpleNamespace(
            run_id=7, dry_run=request.dry_run,
            result=SimpleNamespace(success=1, failure=0, unchanged=0),
            plan=SimpleNamespace(selected=[object()]),
        )


def config(tmp_path: Path) -> AppConfig:
    return AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "out", database=tmp_path / "out" / "backup.db"
    ))


def test_job_manager_records_events_and_result(tmp_path: Path):
    manager = BackupJobManager(config(tmp_path), use_case_factory=SuccessfulUseCase)
    try:
        submitted = manager.submit(BackupRequest(dry_run=True))
        result = manager.wait(submitted["job_id"])
        assert result["status"] == "completed"
        assert result["result"] == {
            "run_id": 7, "dry_run": True, "success": 1,
            "failure": 0, "unchanged": 0, "selected": 1,
        }
        assert [event["kind"] for event in result["events"]] == [
            "plan_ready", "job_finished",
        ]
    finally:
        manager.close()


def test_job_manager_allows_only_one_active_job(tmp_path: Path):
    started = Event()
    release = Event()

    class BlockingUseCase(SuccessfulUseCase):
        def run(self, request):
            started.set()
            release.wait(2)
            return super().run(request)

    manager = BackupJobManager(config(tmp_path), use_case_factory=BlockingUseCase)
    try:
        first = manager.submit(BackupRequest())
        assert started.wait(1)
        with pytest.raises(RuntimeError, match="已有備份工作"):
            manager.submit(BackupRequest())
        release.set()
        assert manager.wait(first["job_id"])["status"] == "completed"
    finally:
        release.set()
        manager.close()


def test_job_manager_cancels_cooperatively(tmp_path: Path):
    started = Event()

    class CancellableUseCase:
        def __init__(self, config, *, sink, cancellation):
            self.cancellation = cancellation

        def run(self, request):
            started.set()
            for _ in range(100):
                if self.cancellation.cancelled:
                    raise BackupCancelled("cancelled")
                time.sleep(0.005)
            raise AssertionError("cancellation did not arrive")

    manager = BackupJobManager(config(tmp_path), use_case_factory=CancellableUseCase)
    try:
        job = manager.submit(BackupRequest())
        assert started.wait(1)
        cancelling = manager.cancel(job["job_id"])
        assert cancelling["status"] == "cancelling"
        assert manager.wait(job["job_id"])["status"] == "cancelled"
    finally:
        manager.close()


def test_completed_job_and_events_survive_manager_restart(tmp_path: Path):
    app_config = config(tmp_path)
    manager = BackupJobManager(app_config, use_case_factory=SuccessfulUseCase)
    try:
        submitted = manager.submit(BackupRequest(dry_run=True, max_posts=3))
        completed = manager.wait(submitted["job_id"])
    finally:
        manager.close()

    restored_manager = BackupJobManager(app_config, use_case_factory=SuccessfulUseCase)
    try:
        restored = restored_manager.get(completed["job_id"])
        assert restored is not None
        assert restored["status"] == "completed"
        assert restored["request"]["max_posts"] == 3
        assert restored["result"]["run_id"] == 7
        assert [event["kind"] for event in restored["events"]] == [
            "plan_ready", "job_finished",
        ]
        summary = restored_manager.list()[0]
        assert summary["job_id"] == completed["job_id"]
        assert summary["event_count"] == 2
        assert "events" not in summary
    finally:
        restored_manager.close()


def test_active_job_is_recovered_as_interrupted(tmp_path: Path):
    app_config = config(tmp_path)
    database = Database(app_config.storage.database)
    timestamp = "2026-10-27T10:00:00+00:00"
    database.create_web_job(
        "abandoned-job", json.dumps({
            "creator": None, "dry_run": False, "max_posts": 20,
            "browser": None, "scope": "supporting", "mode": "full",
        }), timestamp, timestamp,
    )
    database.update_web_job(
        "abandoned-job", status="running", updated_at=timestamp,
        started_at=timestamp, finished_at=None, error=None, result_json=None,
    )
    database.record_web_job_event(
        "abandoned-job", "job_started", timestamp,
        json.dumps({"scope": "supporting"}),
    )

    manager = BackupJobManager(app_config, use_case_factory=SuccessfulUseCase)
    try:
        restored = manager.get("abandoned-job")
        assert restored is not None
        assert restored["status"] == "interrupted"
        assert "不會自動重新執行" in restored["error"]
        assert [event["kind"] for event in restored["events"]] == [
            "job_started", "job_interrupted",
        ]
    finally:
        manager.close()


def test_asset_progress_is_coalesced_in_persistent_events(tmp_path: Path):
    class ProgressUseCase(SuccessfulUseCase):
        def run(self, request):
            self.sink.emit(BackupEvent("asset_progress", {
                "asset_id": "cover", "name": "cover.jpg", "downloaded": 10, "total": 20,
            }))
            self.sink.emit(BackupEvent("asset_progress", {
                "asset_id": "cover", "name": "cover.jpg", "downloaded": 20, "total": 20,
            }))
            return super().run(request)

    app_config = config(tmp_path)
    manager = BackupJobManager(app_config, use_case_factory=ProgressUseCase)
    try:
        submitted = manager.submit(BackupRequest())
        completed = manager.wait(submitted["job_id"])
        progress = [event for event in completed["events"] if event["kind"] == "asset_progress"]
        assert len(progress) == 1
        assert progress[0]["data"]["downloaded"] == 20
        assert len(Database(app_config.storage.database).web_job_event_rows(submitted["job_id"])) == 3
    finally:
        manager.close()


def test_retry_creates_new_job_with_same_request(tmp_path: Path):
    class FailsOnceUseCase(SuccessfulUseCase):
        calls = 0

        def run(self, request):
            type(self).calls += 1
            if type(self).calls == 1:
                raise RuntimeError("temporary failure")
            return super().run(request)

    manager = BackupJobManager(config(tmp_path), use_case_factory=FailsOnceUseCase)
    try:
        first = manager.submit(BackupRequest(
            creators=("alice", "bob"), dry_run=False, max_posts=7,
            scope="creators:alice,bob", mode="full",
            include_profile=False, include_fancard=True,
        ))
        failed = manager.wait(first["job_id"])
        assert failed["status"] == "failed"

        retried = manager.retry(first["job_id"])
        assert retried is not None
        assert retried["job_id"] != first["job_id"]
        completed = manager.wait(retried["job_id"])
        assert completed["status"] == "completed"
        assert completed["request"] == failed["request"]
        assert completed["request"]["creators"] == ("alice", "bob")
        assert completed["request"]["include_profile"] is False
        assert completed["request"]["include_fancard"] is True
        assert manager.get(first["job_id"])["status"] == "failed"
    finally:
        manager.close()


def test_verify_job_uses_same_persistent_queue(tmp_path: Path):
    app_config = config(tmp_path)
    manager = BackupJobManager(app_config, use_case_factory=SuccessfulUseCase)
    try:
        submitted = manager.submit_verify()
        completed = manager.wait(submitted["job_id"])
        assert completed["kind"] == "verify"
        assert completed["status"] == "completed"
        assert completed["result"] == {
            "passed": True, "issue_count": 0, "issues": [], "truncated": False,
        }
        assert [event["kind"] for event in completed["events"]] == [
            "verify_started", "verify_finished",
        ]
        assert manager.list()[0]["kind"] == "verify"
    finally:
        manager.close()
