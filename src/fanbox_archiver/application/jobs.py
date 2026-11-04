from __future__ import annotations

import json
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Callable

from ..archive_lock import ArchiveLock
from ..config import AppConfig
from ..database import Database
from ..i18n import Text, decode_text, decode_texts, encode_texts, error_text
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
    """Run at most one archive mutation at a time in a background worker.

    History lives in SQLite and is paged from there; memory only holds jobs run by
    this process, so the active job's live state wins over its persisted row.

    With an ``archive_lock`` the manager also respects jobs run by another process
    (the background scheduled backup): while that process owns the archive this
    manager reports itself busy and never marks the other process's job interrupted.
    """

    EXTERNAL_BUSY = Text("jobs.external_busy")

    _FINISHED_IN_MEMORY = 10
    _ACTIVE = frozenset({"queued", "running", "cancelling"})

    def __init__(
        self, config: AppConfig, *,
        use_case_factory: Callable[..., BackupUseCase] = BackupUseCase,
        archive_lock: ArchiveLock | None = None,
    ) -> None:
        self.config = config
        self.use_case_factory = use_case_factory
        self.db = Database(config.storage.database)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fanbox-backup")
        self._lock = Lock()
        self._jobs: dict[str, BackupJob] = {}
        self._futures: dict[str, Future] = {}
        self._progress_persisted_at: dict[str, float] = {}
        self.archive_lock = archive_lock
        self._recovered = False
        self._external_busy()

    def submit(self, request: BackupRequest) -> dict[str, Any]:
        return self._submit("backup", request)

    def submit_verify(self) -> dict[str, Any]:
        return self._submit("verify", {})

    def _submit(self, kind: str, request: Any) -> dict[str, Any]:
        with self._lock:
            return self._submit_locked(kind, request)

    def _submit_locked(self, kind: str, request: Any) -> dict[str, Any]:
        if any(job.status in self._ACTIVE for job in self._jobs.values()):
            raise RuntimeError(Text("jobs.already_running"))
        if self._external_busy():
            raise RuntimeError(self.EXTERNAL_BUSY)
        job_id = uuid.uuid4().hex
        job = BackupJob(job_id, request, CancellationToken(), kind=kind)
        self._jobs[job_id] = job
        self.db.create_web_job(
            job.job_id, json.dumps(self._request_data(job.request), ensure_ascii=False, sort_keys=True),
            job.created_at, job.updated_at, kind=kind,
        )
        self._futures[job_id] = self._executor.submit(self._run, job_id)
        return self._snapshot(job)

    def page(
        self, *, kind: str | None = None, status: str | None = None, ascending: bool = False,
        page: int = 1, page_size: int = 20,
    ) -> dict[str, Any]:
        page_size = min(max(1, page_size), 100)
        total = self.db.web_job_count(kind=kind, status=status)
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(max(1, page), pages)
        rows = self.db.web_job_page(
            kind=kind, status=status, ascending=ascending,
            limit=page_size, offset=(page - 1) * page_size,
        )
        with self._lock:
            items = [
                self._snapshot(self._jobs[str(row["job_id"])], include_events=False)
                if str(row["job_id"]) in self._jobs else self._row_snapshot(row)
                for row in rows
            ]
            active = next((job for job in self._jobs.values() if job.status in self._ACTIVE), None)
            active_value = self._snapshot(active, include_events=False) if active else None
        if active_value is None and self._external_busy():
            running = self.db.web_job_page(status="running", limit=1)
            if running:
                active_value = {**self._row_snapshot(running[0]), "external": True}
        return {
            "items": items, "page": page, "pages": pages, "page_size": page_size,
            "total": total, "active": active_value,
        }

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                return self._snapshot(job)
        row = self.db.web_job_row(job_id)
        return self._row_snapshot(row, include_events=True) if row is not None else None

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                # Only jobs run by this process can still be active; older ones are final.
                row = self.db.web_job_row(job_id)
                return self._row_snapshot(row, include_events=True) if row is not None else None
            if job.kind != "backup" and job.status in {"queued", "running", "cancelling"}:
                raise RuntimeError(Text("jobs.cannot_cancel"))
            if job.status in {"queued", "running"}:
                job.cancellation.cancel()
                job.status = "cancelling"
                job.updated_at = _now()
                self._persist_job(job)
            return self._snapshot(job)

    def retry(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                if job.status in self._ACTIVE:
                    raise RuntimeError(Text("jobs.cannot_retry_running"))
                return self._submit_locked(job.kind, job.request)
        row = self.db.web_job_row(job_id)
        if row is None:
            return None
        kind = str(row["kind"])
        request_data = json.loads(str(row["request_json"]))
        request = self._restore_backup_request(request_data) if kind == "backup" else request_data
        return self._submit(kind, request)

    def has_active(self) -> bool:
        with self._lock:
            if any(job.status in self._ACTIVE for job in self._jobs.values()):
                return True
        return self._external_busy()

    def _external_busy(self) -> bool:
        """True while another process owns the archive; take ownership as soon as it is free."""
        if self.archive_lock is not None and not self.archive_lock.try_acquire():
            return True
        if not self._recovered:
            # Rows still "running" now belong to nobody, so they were interrupted.
            self._recovered = True
            self.db.recover_interrupted_web_jobs(_now())
        return False

    def wait(self, job_id: str, timeout: float = 10.0) -> dict[str, Any]:
        with self._lock:
            future = self._futures.get(job_id)
        if future is not None:
            future.result(timeout=timeout)
        result = self.get(job_id)
        if result is None:
            raise KeyError(job_id)
        return result

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)
        if self.archive_lock is not None:
            self.archive_lock.release()

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
                issues = ArchiveService(self.config).verify(
                    lambda data: self._record_event(
                        job_id, BackupEvent("verify_progress", data),
                    )
                )
                # Python mode keeps each reason as ``Text`` so the reader can show it in its language.
                issue_values = [issue.model_dump() for issue in issues[:500]]
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
                job.error = error_text(exc)
        except Exception as exc:
            with self._lock:
                job.status = "failed"
                job.error = error_text(exc)
        finally:
            with self._lock:
                if job.kind == "verify" and job.status != "completed":
                    progress = next(
                        (value for value in reversed(job.events)
                         if value["kind"] == "verify_progress"),
                        None,
                    )
                    if progress is not None:
                        self.db.record_web_job_event(
                            job_id, "verify_progress", progress["timestamp"],
                            json.dumps(
                                encode_texts(progress["data"]), ensure_ascii=False, sort_keys=True,
                            ),
                            coalesce_key="verify-progress",
                        )
                job.finished_at = job.updated_at = _now()
                self._persist_job(job)
                self._forget_finished()

    def _forget_finished(self) -> None:
        finished = [key for key, value in self._jobs.items() if value.status not in self._ACTIVE]
        for key in finished[:-self._FINISHED_IN_MEMORY]:
            del self._jobs[key]
            self._futures.pop(key, None)

    def _record_event(self, job_id: str, event: BackupEvent) -> None:
        value = event.model_dump()
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            previous_progress = None
            replace_progress = (
                event.kind == "asset_progress" and job.events
                and job.events[-1]["kind"] == "asset_progress"
                and job.events[-1]["data"].get("asset_id") == event.data.get("asset_id")
            ) or (
                event.kind == "verify_progress" and job.events
                and job.events[-1]["kind"] == "verify_progress"
            )
            if replace_progress:
                previous_progress = job.events[-1]["data"]
                job.events[-1] = value
            else:
                job.events.append(value)
                if len(job.events) > 1000:
                    del job.events[:100]
            job.updated_at = _now()
            coalesce_key = (
                f"asset:{event.data.get('asset_id')}"
                if event.kind == "asset_progress"
                else "verify-progress" if event.kind == "verify_progress" else None
            )
            if event.kind in {"asset_progress", "verify_progress"}:
                current = time.monotonic()
                if event.kind == "asset_progress":
                    total = event.data.get("total")
                    force = total is not None and event.data.get("downloaded", 0) >= total
                else:
                    total = event.data.get("total")
                    force = (
                        previous_progress is None
                        or previous_progress.get("phase") != event.data.get("phase")
                        or previous_progress.get("total") != total
                        or total is not None and event.data.get("current", 0) >= total
                    )
                if not force and current - self._progress_persisted_at.get(job_id, 0.0) < 0.5:
                    return
                self._progress_persisted_at[job_id] = current
            self.db.record_web_job_event(
                job_id, event.kind, event.timestamp,
                json.dumps(encode_texts(event.data), ensure_ascii=False, sort_keys=True),
                coalesce_key=coalesce_key,
            )
            self._persist_job(job)

    def _row_snapshot(self, row: Any, *, include_events: bool = False) -> dict[str, Any]:
        value = {
            "job_id": str(row["job_id"]),
            "kind": str(row["kind"]),
            "status": str(row["status"]),
            "request": json.loads(str(row["request_json"])),
            "created_at": str(row["created_at"]),
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "updated_at": str(row["updated_at"]),
            "error": decode_text(row["error"]),
            "result": decode_texts(json.loads(str(row["result_json"]))) if row["result_json"] else None,
            "event_count": int(row["event_count"]),
        }
        if include_events:
            value["events"] = [
                {
                    "kind": str(event["kind"]),
                    "timestamp": str(event["timestamp"]),
                    "data": decode_texts(json.loads(str(event["data_json"]))),
                }
                for event in self.db.web_job_event_rows(value["job_id"])
            ]
        return value

    def _persist_job(self, job: BackupJob) -> None:
        self.db.update_web_job(
            job.job_id,
            status=job.status,
            updated_at=job.updated_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            error=job.error.encode() if isinstance(job.error, Text) else job.error,
            result_json=(
                json.dumps(encode_texts(job.result), ensure_ascii=False, sort_keys=True)
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

    @staticmethod
    def _restore_backup_request(value: dict[str, Any]) -> BackupRequest:
        data = dict(value)
        data["creators"] = tuple(data.get("creators") or ())
        data["posts"] = tuple(data.get("posts") or ())
        return BackupRequest(**data)
