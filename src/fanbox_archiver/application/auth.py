from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import Event, Lock
from typing import Any, Callable

from ..browser_session import (
    BrowserLoginCancelled,
    BrowserLoginError,
    clear_profile_authentication,
    interactive_login,
    profile_is_authenticated,
)
from ..client import FanboxClient
from ..config import AppConfig


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class AuthStatus:
    state: str
    source: str
    message: str
    can_login: bool
    can_logout: bool
    externally_managed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuthenticationService:
    """Authentication operations shared by CLI and the local GUI."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def check(self) -> AuthStatus:
        profile = self.config.auth.profile_dir
        if profile.exists():
            try:
                authenticated = profile_is_authenticated(
                    profile, channel=self.config.auth.browser_channel
                )
            except BrowserLoginError as exc:
                return AuthStatus("error", "profile", str(exc), True, True)
            if authenticated:
                return AuthStatus(
                    "authenticated", "profile", "專用瀏覽器工作階段有效。", True, True
                )
            return AuthStatus(
                "expired", "profile", "專用瀏覽器工作階段已失效，請重新登入。", True, True
            )

        cookie = os.environ.get("FANBOX_COOKIE", "").strip()
        if not cookie:
            return AuthStatus(
                "signed_out", "none", "尚未建立 FANBOX 登入工作階段。", True, False
            )
        try:
            with FanboxClient(
                cookie=cookie,
                timeout=self.config.download.timeout_seconds,
                request_interval=self.config.download.request_interval_seconds,
            ) as client:
                authenticated = client.verify_auth()
        except Exception as exc:
            return AuthStatus(
                "error", "environment", f"無法檢查外部管理的登入狀態：{type(exc).__name__}",
                True, False, True,
            )
        return AuthStatus(
            "authenticated" if authenticated else "expired",
            "environment",
            ("外部 FANBOX_COOKIE 有效。" if authenticated else
             "外部 FANBOX_COOKIE 已失效；請在啟動環境中更新或移除。"),
            True, False, True,
        )

    def login(
        self, *, timeout_seconds: int = 600, should_cancel: Callable[[], bool] | None = None,
    ) -> AuthStatus:
        interactive_login(
            self.config.auth.profile_dir,
            channel=self.config.auth.browser_channel,
            timeout_seconds=timeout_seconds,
            should_cancel=should_cancel,
        )
        return self.check()

    def logout(self) -> AuthStatus:
        if not self.config.auth.profile_dir.exists():
            if os.environ.get("FANBOX_COOKIE", "").strip():
                raise RuntimeError("登入由 FANBOX_COOKIE 外部管理，無法由應用程式撤銷")
            return self.check()
        clear_profile_authentication(
            self.config.auth.profile_dir, channel=self.config.auth.browser_channel
        )
        return AuthStatus(
            "signed_out", "profile", "已清除專用 FANBOX 工作階段。", True, False
        )


class AuthenticationJobManager:
    """Run one cancellable interactive-login window at a time."""

    def __init__(self, service: AuthenticationService) -> None:
        self.service = service
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fanbox-auth")
        self._lock = Lock()
        self._job: dict[str, Any] | None = None
        self._cancel = Event()

    def start(self, *, timeout_seconds: int = 600) -> dict[str, Any]:
        with self._lock:
            if self._job and self._job["status"] in {"queued", "running", "cancelling"}:
                raise RuntimeError("登入視窗已在執行")
            self._cancel = Event()
            self._job = {
                "job_id": uuid.uuid4().hex,
                "status": "queued",
                "created_at": _now(),
                "finished_at": None,
                "error": None,
                "result": None,
            }
            job_id = self._job["job_id"]
            self._executor.submit(self._run, job_id, timeout_seconds)
            return dict(self._job)

    def active(self) -> dict[str, Any] | None:
        with self._lock:
            if self._job and self._job["status"] in {"queued", "running", "cancelling"}:
                return dict(self._job)
            return None

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._job) if self._job and self._job["job_id"] == job_id else None

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            if not self._job or self._job["job_id"] != job_id:
                return None
            if self._job["status"] in {"queued", "running"}:
                self._job["status"] = "cancelling"
                self._cancel.set()
            return dict(self._job)

    def close(self) -> None:
        self._cancel.set()
        self._executor.shutdown(wait=False, cancel_futures=False)

    def _run(self, job_id: str, timeout_seconds: int) -> None:
        with self._lock:
            if not self._job or self._job["job_id"] != job_id:
                return
            self._job["status"] = "running"
        try:
            result = self.service.login(
                timeout_seconds=timeout_seconds, should_cancel=self._cancel.is_set
            )
            with self._lock:
                self._job["status"] = "completed"
                self._job["result"] = result.as_dict()
        except BrowserLoginCancelled as exc:
            with self._lock:
                self._job["status"] = "cancelled"
                self._job["error"] = str(exc)
        except Exception as exc:
            with self._lock:
                self._job["status"] = "failed"
                self._job["error"] = str(exc)
        finally:
            with self._lock:
                if self._job and self._job["job_id"] == job_id:
                    self._job["finished_at"] = _now()
