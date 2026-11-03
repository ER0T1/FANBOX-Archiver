from __future__ import annotations

from datetime import UTC, datetime
from threading import Event, Lock, Thread
from typing import Any, Callable

from ..config import AppConfig
from ..database import Database
from .. import power
from ..schedule import count_between, describe, latest_due, next_run
from ..timestamps import display_zone, format_display, parse_instant
from .backup import BackupRequest
from .jobs import BackupJobManager


def _now() -> datetime:
    return datetime.now(UTC)


class BackupScheduler:
    """Submit scheduled backups through the shared job manager while the app runs.

    Only the latest due occurrence is ever run, so any number of missed occurrences
    (app closed, PC asleep) collapse into a single catch-up. An occurrence that comes
    due while another job runs is deferred and submitted once that job finishes.
    """

    def __init__(
        self, get_config: Callable[[], AppConfig], get_jobs: Callable[[], BackupJobManager],
        db: Database, *, is_busy: Callable[[], bool] = lambda: False,
        clock: Callable[[], datetime] = _now, interval: float = 30.0,
        on_battery: Callable[[], bool] | None = None,
    ) -> None:
        self.get_config = get_config
        self.get_jobs = get_jobs
        self.db = db
        self.is_busy = is_busy
        self.clock = clock
        self.interval = interval
        self.on_battery = on_battery or (lambda: power.on_battery())
        self._stop = Event()
        self._lock = Lock()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = Thread(target=self._loop, name="fanbox-scheduler", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - one bad tick must not stop the schedule
                continue

    def reset(self) -> None:
        """Start counting from now, e.g. after the schedule was edited."""
        with self._lock:
            self.db.set_schedule_state(
                handled_through=self.clock().isoformat(), deferred_due=None, note=None,
            )

    def tick(self) -> str | None:
        with self._lock:
            config = self.get_config()
            schedule = config.schedule
            if not schedule.enabled:
                return None
            now = self.clock()
            state = self.db.schedule_state()
            handled = parse_instant(state["handled_through"]) if state else None
            if handled is None:
                # First tick after enabling: never fire for times before the schedule existed.
                self.db.set_schedule_state(handled_through=now.isoformat())
                return None
            due = latest_due(schedule, now)
            if due is None or due <= handled:
                return None
            due_iso = due.isoformat()
            if schedule.power == "no_wake_ac_only" and self.on_battery():
                if state["deferred_due"] != due_iso:
                    self.db.set_schedule_state(
                        deferred_due=due_iso,
                        note=f"{format_display(due)} 的排程遇到使用電池中，將於接上電源後執行。",
                    )
                return "deferred"
            jobs = self.get_jobs()
            if self.is_busy() or jobs.has_active():
                if state["deferred_due"] != due_iso:
                    self.db.set_schedule_state(
                        deferred_due=due_iso,
                        note=f"{format_display(due)} 的排程遇到其他工作執行中，將於該工作結束後執行。",
                    )
                return "deferred"
            try:
                job = jobs.submit(self._request(config))
            except RuntimeError:
                return "deferred"
            missed = count_between(schedule, handled, due)
            if missed > 1:
                note = f"錯過 {missed} 次排程，已補跑最近一次（{format_display(due)}）。"
            elif state["deferred_due"] == due_iso:
                note = f"{format_display(due)} 的排程曾延後，已於可以執行時補跑。"
            elif (now - due).total_seconds() > max(120.0, self.interval * 4):
                note = f"已補跑錯過的排程（{format_display(due)}）。"
            else:
                note = None
            self.db.set_schedule_state(
                handled_through=due_iso, last_due_at=due_iso, last_job_id=job["job_id"],
                deferred_due=None, note=note,
            )
            return "submitted"

    def run_now(self) -> dict[str, Any]:
        """Run the scheduled backup once immediately; the schedule itself is unchanged."""
        if self.is_busy():
            raise RuntimeError("登入工作執行期間無法開始備份")
        return self.get_jobs().submit(self._request(self.get_config()))

    def status(self) -> dict[str, Any]:
        config = self.get_config()
        schedule = config.schedule
        state = self.db.schedule_state()
        last_job = None
        if state and state["last_job_id"]:
            job = self.get_jobs().get(str(state["last_job_id"]))
            if job is not None:
                last_job = {
                    key: job.get(key)
                    for key in ("job_id", "status", "error", "created_at", "finished_at", "result")
                }
        return {
            "enabled": schedule.enabled,
            "summary": describe(schedule),
            "timezone": display_zone().name,
            "next_run_at": next_run(schedule, self.clock()).isoformat() if schedule.enabled else None,
            "last_due_at": state["last_due_at"] if state else None,
            "deferred_due": state["deferred_due"] if state else None,
            "note": state["note"] if state else None,
            "last_job": last_job,
        }

    @staticmethod
    def _request(config: AppConfig) -> BackupRequest:
        creators = tuple(dict.fromkeys(config.schedule.creators))
        base_scope = (
            "supporting" if not creators else
            f"creator:{creators[0]}" if len(creators) == 1 else
            f"creators:{','.join(creators)}"
        )
        return BackupRequest(
            creators=creators, dry_run=False, scope=base_scope, mode="full",
            include_profile=config.backup_defaults.include_profile,
            include_fancard=config.backup_defaults.include_fancard,
            trigger="schedule",
        )
