from __future__ import annotations

import json
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Callable

from ..config import AppConfig
from ..database import Database
from ..service import ArchiveService
from .backup import BackupRequest, BackupUseCase
from .events import BackupCancelled, BackupEvent, CancellationToken, EventSink


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class BackupJob:
    job_id: str
    request: Any
    cancellation: CancellationToken
    kind: str = "backup"
    status: str = "queued"
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str = field(default_factory=_now)
    error: str | None = None
    result: dict[str, Any] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)


class _JobEventSink(EventSink):
    def __init__(self, manager: "BackupJobManager", job_id: str):
        self.manager = manager
        self.job_id = job_id

    def emit(self, event: BackupEvent) -> None:
        self.manager._record_event(self.job_id, event)


class BackupJobManager:
    """Run at most one archive mutation at a time in a background worker."""

    def __init__(
        self, config: AppConfig, *,
        use_case_factory: Callable[..., BackupUseCase] = BackupUseCase,
    ) -> None:
        self.config = config
        self.use_case_factory = use_case_factory
        self.db = Database(config.storage.database)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fanbox-backup")
        self._lock = Lock()
        self._jobs: dict[str, BackupJob] = {}
        self._futures: dict[str, Future] = {}
        self._progress_persisted_at: dict[str, float] = {}
        self.db.recover_interrupted_web_jobs(_now())
        self._restore_jobs()

    def submit(self, request: BackupRequest) -> dict[str, Any]:
        return self._submit("backup", request)

    def submit_verify(self) -> dict[str, Any]:
        return self._submit("verify", {})

    def _submit(self, kind: str, request: Any) -> dict[str, Any]:
        with self._lock:
            if any(job.status in {"queued", "running", "cancelling"} for job in self._jobs.values()):
                raise RuntimeError("已有備份工作正在執行")
            job_id = uuid.uuid4().hex
            job = BackupJob(job_id, request, CancellationToken(), kind=kind)
            self._jobs[job_id] = job
            self.db.create_web_job(
                job.job_id, json.dumps(self._request_data(job.request), ensure_ascii=False, sort_keys=True),
                job.created_at, job.updated_at, kind=kind,
            )
            self._futures[job_id] = self._executor.submit(self._run, job_id)
            return self._snapshot(job)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                self._snapshot(job, include_events=False)
                for job in reversed(list(self._jobs.values()))
            ]

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return self._snapshot(job) if job else None

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.kind != "backup" and job.status in {"queued", "running", "cancelling"}:
                raise RuntimeError("此類工作不支援中途取消")
            if job.status in {"queued", "running"}:
                job.cancellation.cancel()
                job.status = "cancelling"
                job.updated_at = _now()
                self._persist_job(job)
            return self._snapshot(job)

    def retry(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status in {"queued", "running", "cancelling"}:
                raise RuntimeError("工作仍在執行，無法重試")
            request = job.request
            kind = job.kind
        return self._submit(kind, request)

    def has_active(self) -> bool:
        with self._lock:
            return any(
                job.status in {"queued", "running", "cancelling"}
                for job in self._jobs.values()
            )

    def wait(self, job_id: str, timeout: float = 10.0) -> dict[str, Any]:
        with self._lock:
            future = self._futures[job_id]
        future.result(timeout=timeout)
        result = self.get(job_id)
        if result is None:
            raise KeyError(job_id)
        return result

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job.cancellation.cancelled:
                job.status = "cancelled"
                job.finished_at = job.updated_at = _now()
                self._persist_job(job)
                return
            job.status = "running"
            job.started_at = job.updated_at = _now()
            self._persist_job(job)
        try:
            if job.kind == "verify":
                self._record_event(job_id, BackupEvent("verify_started"))
                issues = ArchiveService(self.config).verify()
                issue_values = [issue.model_dump(mode="json") for issue in issues[:500]]
                self._record_event(job_id, BackupEvent(
                    "verify_finished", {"issue_count": len(issues), "shown": len(issue_values)},
                ))
                with self._lock:
                    job.status = "completed"
                    job.result = {
                        "passed": not issues,
                        "issue_count": len(issues),
                        "issues": issue_values,
                        "truncated": len(issues) > len(issue_values),
                    }
            else:
                outcome = self.use_case_factory(
                    self.config,
                    sink=_JobEventSink(self, job_id),
                    cancellation=job.cancellation,
                ).run(job.request)
                with self._lock:
                    job.status = "completed"
                    job.result = {
                        "run_id": outcome.run_id,
                        "dry_run": outcome.dry_run,
                        "success": outcome.result.success if outcome.result else 0,
                        "failure": outcome.result.failure if outcome.result else 0,
                        "unchanged": outcome.result.unchanged if outcome.result else 0,
                        "selected": len(outcome.plan.selected),
                    }
        except BackupCancelled as exc:
            with self._lock:
                job.status = "cancelled"
                job.error = str(exc)
        except Exception as exc:
            with self._lock:
                job.status = "failed"
                job.error = str(exc)
        finally:
            with self._lock:
                job.finished_at = job.updated_at = _now()
                self._persist_job(job)

    def _record_event(self, job_id: str, event: BackupEvent) -> None:
        value = event.model_dump()
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if (
                event.kind == "asset_progress" and job.events
                and job.events[-1]["kind"] == "asset_progress"
                and job.events[-1]["data"].get("asset_id") == event.data.get("asset_id")
            ):
                job.events[-1] = value
            else:
                job.events.append(value)
                if len(job.events) > 1000:
                    del job.events[:100]
            job.updated_at = _now()
            coalesce_key = (
                f"asset:{event.data.get('asset_id')}"
                if event.kind == "asset_progress" else None
            )
            if event.kind == "asset_progress":
                current = time.monotonic()
                total = event.data.get("total")
                finished = total is not None and event.data.get("downloaded", 0) >= total
                if not finished and current - self._progress_persisted_at.get(job_id, 0.0) < 0.5:
                    return
                self._progress_persisted_at[job_id] = current
            self.db.record_web_job_event(
                job_id, event.kind, event.timestamp,
                json.dumps(event.data, ensure_ascii=False, sort_keys=True),
                coalesce_key=coalesce_key,
            )
            self._persist_job(job)

    def _restore_jobs(self) -> None:
        for row in reversed(self.db.web_job_rows()):
            request_data = json.loads(str(row["request_json"]))
            kind = str(row["kind"])
            result = json.loads(str(row["result_json"])) if row["result_json"] else None
            events = [
                {
                    "kind": str(event["kind"]),
                    "timestamp": str(event["timestamp"]),
                    "data": json.loads(str(event["data_json"])),
                }
                for event in self.db.web_job_event_rows(str(row["job_id"]))
            ]
            self._jobs[str(row["job_id"])] = BackupJob(
                job_id=str(row["job_id"]),
                request=(BackupRequest(**request_data) if kind == "backup" else request_data),
                cancellation=CancellationToken(),
                kind=kind,
                status=str(row["status"]),
                created_at=str(row["created_at"]),
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                updated_at=str(row["updated_at"]),
                error=row["error"],
                result=result,
                events=events,
            )

    def _persist_job(self, job: BackupJob) -> None:
        self.db.update_web_job(
            job.job_id,
            status=job.status,
            updated_at=job.updated_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            error=job.error,
            result_json=(
                json.dumps(job.result, ensure_ascii=False, sort_keys=True)
                if job.result is not None else None
            ),
        )

    @staticmethod
    def _snapshot(job: BackupJob, *, include_events: bool = True) -> dict[str, Any]:
        value = {
            "job_id": job.job_id,
            "kind": job.kind,
            "status": job.status,
            "request": BackupJobManager._request_data(job.request),
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "updated_at": job.updated_at,
            "error": job.error,
            "result": job.result,
            "event_count": len(job.events),
        }
        if include_events:
            value["events"] = list(job.events)
        return value

    @staticmethod
    def _request_data(request: Any) -> dict[str, Any]:
        if is_dataclass(request):
            return asdict(request)
        return dict(request)
