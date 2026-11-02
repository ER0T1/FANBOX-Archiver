from __future__ import annotations

import time

import pytest

from fanbox_archiver.application.auth import (
    AuthenticationJobManager,
    AuthenticationService,
    AuthStatus,
)
from fanbox_archiver.browser_session import BrowserLoginCancelled
from fanbox_archiver.browser_session import BrowserLoginError
from fanbox_archiver.config import AppConfig, AuthConfig


def auth_config(tmp_path):
    return AppConfig(auth=AuthConfig(profile_dir=tmp_path / "profile"))


def test_auth_status_distinguishes_signed_out_profile_and_external(tmp_path, monkeypatch):
    config = auth_config(tmp_path)
    service = AuthenticationService(config)
    monkeypatch.delenv("FANBOX_COOKIE", raising=False)
    assert service.check().state == "signed_out"

    config.auth.profile_dir.mkdir()
    monkeypatch.setattr("fanbox_archiver.application.auth.profile_is_authenticated", lambda *_a, **_k: True)
    profile = service.check()
    assert (profile.state, profile.source, profile.can_logout) == ("authenticated", "profile", True)

    config.auth.profile_dir.rmdir()
    monkeypatch.setenv("FANBOX_COOKIE", "secret-cookie-value")

    class Client:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def verify_auth(self): return True

    monkeypatch.setattr("fanbox_archiver.application.auth.FanboxClient", Client)
    external = service.check()
    assert external.source == "environment"
    assert external.externally_managed is True
    assert external.can_logout is False
    assert "secret-cookie-value" not in external.message


def test_logout_only_clears_dedicated_profile(tmp_path, monkeypatch):
    config = auth_config(tmp_path)
    config.auth.profile_dir.mkdir()
    cleared = []
    monkeypatch.setattr(
        "fanbox_archiver.application.auth.clear_profile_authentication",
        lambda path, **_kwargs: cleared.append(path),
    )
    status = AuthenticationService(config).logout()
    assert cleared == [config.auth.profile_dir]
    assert status.state == "signed_out"


def test_profile_lock_and_login_timeout_are_understandable(tmp_path, monkeypatch):
    config = auth_config(tmp_path)
    config.auth.profile_dir.mkdir()
    monkeypatch.setattr(
        "fanbox_archiver.application.auth.profile_is_authenticated",
        lambda *_a, **_k: (_ for _ in ()).throw(BrowserLoginError("請先關閉登入視窗後重試")),
    )
    status = AuthenticationService(config).check()
    assert status.state == "error"
    assert "關閉登入視窗" in status.message

    class TimeoutService:
        def login(self, **_kwargs):
            raise BrowserLoginError("等待 FANBOX 登入逾時")

    manager = AuthenticationJobManager(TimeoutService())
    try:
        job = manager.start(timeout_seconds=60)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            result = manager.get(job["job_id"])
            if result and result["status"] == "failed":
                break
            time.sleep(.01)
        assert result["status"] == "failed"
        assert result["error"] == "等待 FANBOX 登入逾時"
    finally:
        manager.close()


def test_external_cookie_cannot_be_logged_out_in_app(tmp_path, monkeypatch):
    monkeypatch.setenv("FANBOX_COOKIE", "externally-managed")
    with pytest.raises(RuntimeError, match="外部管理"):
        AuthenticationService(auth_config(tmp_path)).logout()


def test_login_job_can_be_cancelled():
    class Service:
        def login(self, *, should_cancel, **_kwargs):
            while not should_cancel():
                time.sleep(.01)
            raise BrowserLoginCancelled("登入已取消")

    manager = AuthenticationJobManager(Service())
    try:
        job = manager.start(timeout_seconds=60)
        manager.cancel(job["job_id"])
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            result = manager.get(job["job_id"])
            if result and result["status"] == "cancelled":
                break
            time.sleep(.01)
        assert result["status"] == "cancelled"
        assert result["error"] == "登入已取消"
    finally:
        manager.close()
