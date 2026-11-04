from pathlib import Path

import httpx
import pytest

from fanbox_archiver.webapp import create_app
from test_reader import dynamic_archive


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_dynamic_web_reader_does_not_require_index(tmp_path: Path):
    config, _ = dynamic_archive(tmp_path)
    transport = httpx.ASGITransport(app=create_app(config))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        home = await client.get("/")
        assert home.status_code == 200
        assert "FANBOX Archive" in home.text
        assert 'data-view="posts">投稿' in home.text
        assert 'data-view="fancards"' not in home.text
        assert "/assets/core.js" in home.text
        assert "/assets/design-tokens.css" in home.text
        assert "/assets/app-v2.js" not in home.text
        assert not (config.storage.output_dir / "_site").exists()

        desktop = await client.get("/assets/desktop.html")
        assert desktop.status_code == 200
        assert "選擇你的本機封存" in desktop.text
        assert 'data-command="choose_existing_config"' in desktop.text
        assert 'data-command="choose_archive_folder"' in desktop.text
        assert 'data-command="use_default_config"' in desktop.text
        assert 'href="design-tokens.css"' in desktop.text

        tokens = await client.get("/assets/design-tokens.css")
        assert tokens.status_code == 200
        assert "--accent:#db6611" in tokens.text

        listing = await client.get("/api/posts")
        assert listing.status_code == 200
        assert listing.json()["items"][0]["title"] == "第二版"
        assert listing.json()["items"][0]["fee_required"] == 500

        tagged = await client.get("/api/posts?creator=alice&tag=測試")
        assert tagged.status_code == 200
        assert tagged.json()["total"] == 1
        assert tagged.json()["creator_total"] == 1
        assert tagged.json()["tag_facets"] == [{"name": "測試", "count": 1}]

        post = await client.get("/api/posts/123")
        assert post.status_code == 200
        assert post.json()["version"] == 2
        assert post.json()["navigation"] == {
            "previous": None, "next": None, "position": 1, "total": 1,
        }
        tagged_post = await client.get("/api/posts/123?creator=alice&tag=測試")
        assert tagged_post.json()["navigation"]["position"] == 1
        assert post.headers["cache-control"] == "no-store"

        creators = await client.get("/api/creators")
        assert creators.status_code == 200
        assert creators.json()["items"][0]["creator_id"] == "alice"

        creator = await client.get("/api/creators/alice")
        assert creator.status_code == 200
        assert creator.json()["fancard_count"] == 1
        assert creator.json()["fanbox_url"] == "https://www.fanbox.cc/@alice"

        cards = await client.get("/api/fancards")
        assert cards.status_code == 200
        assert cards.json()["items"][0]["plan_title"] == "Gold"

        card = await client.get("/api/fancards/alice/2026-10")
        assert card.status_code == 200
        assert card.json()["description"] == "Password: private"
        assert card.json()["perks"][0]["status"] == "accessible"
        assert card.json()["perks"][0]["label"] == "加入 Discord 伺服器"
        assert card.json()["perks"][0]["settings_url"] == "https://www.fanbox.cc/user/settings"
        assert card.json()["perks"][0]["action_url"] == "https://www.fanbox.cc/@alice/plans"
        assert "supporterAccessible" not in str(card.json()["perks"])

        image = await client.get("/api/fancards/alice/2026-10/versions/1/image")
        assert image.status_code == 200
        assert image.content == b"jpeg-data"


@pytest.mark.anyio
async def test_dynamic_web_reader_returns_404_for_unknown_version(tmp_path: Path):
    config, _ = dynamic_archive(tmp_path)
    transport = httpx.ASGITransport(app=create_app(config))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/posts/123?version=99")
        assert response.status_code == 404


@pytest.mark.anyio
async def test_dynamic_web_reader_sets_security_headers(tmp_path: Path):
    config, _ = dynamic_archive(tmp_path)
    transport = httpx.ASGITransport(app=create_app(config))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "object-src 'none'" in response.headers["content-security-policy"]
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
async def test_dynamic_web_reader_rejects_untrusted_host(tmp_path: Path):
    config, _ = dynamic_archive(tmp_path)
    transport = httpx.ASGITransport(app=create_app(config))
    async with httpx.AsyncClient(transport=transport, base_url="http://example.test") as client:
        response = await client.get("/api/posts")
        assert response.status_code == 400


@pytest.mark.anyio
async def test_backup_job_mutations_require_session_token(tmp_path: Path):
    config, _ = dynamic_archive(tmp_path)
    app = create_app(config)

    class StubJobs:
        submitted = []

        def submit(self, request):
            self.submitted.append(request)
            return {"job_id": "job-1", "status": "queued"}

        def list(self):
            return []

        def retry(self, job_id):
            return {"job_id": "job-2", "retried_from": job_id, "status": "queued"}

    app.state.jobs = StubJobs()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post("/api/jobs/backup", json={"dry_run": True})
        assert denied.status_code == 403
        denied_retry = await client.post("/api/jobs/job-1/retry")
        assert denied_retry.status_code == 403

        accepted = await client.post(
            "/api/jobs/backup",
            json={
                "creators": [
                    "https://www.fanbox.cc/@alice", "https://bob.fanbox.cc", "alice",
                ],
                "dry_run": True, "max_posts": 3,
                "include_profile": False, "include_fancard": True,
            },
            headers={"X-Fanbox-Token": app.state.session_token},
        )
        assert accepted.status_code == 202
        assert accepted.json()["job_id"] == "job-1"
        request = app.state.jobs.submitted[-1]
        assert request.mode == "full"
        assert request.creators == ("alice", "bob")
        assert request.scope == "creators:alice,bob"
        assert request.include_profile is False
        assert request.include_fancard is True

        all_creators = await client.post(
            "/api/jobs/backup", json={"creators": [], "dry_run": False},
            headers={"X-Fanbox-Token": app.state.session_token},
        )
        assert all_creators.status_code == 202
        assert app.state.jobs.submitted[-1].creators == ()
        assert app.state.jobs.submitted[-1].scope == "supporting"

        profile = await client.post(
            "/api/jobs/backup",
            json={"creator": "alice", "dry_run": False, "mode": "profile"},
            headers={"X-Fanbox-Token": app.state.session_token},
        )
        assert profile.status_code == 202
        assert app.state.jobs.submitted[-1].mode == "profile"
        assert app.state.jobs.submitted[-1].creators == ("alice",)
        assert app.state.jobs.submitted[-1].scope == "creator:alice:profile"

        retry = await client.post(
            "/api/jobs/job-1/retry",
            headers={"X-Fanbox-Token": app.state.session_token},
        )
        assert retry.status_code == 202
        assert retry.json()["retried_from"] == "job-1"


@pytest.mark.anyio
async def test_web_settings_are_validated_and_saved(tmp_path: Path):
    config, _ = dynamic_archive(tmp_path)
    config_path = tmp_path / "config.yaml"
    app = create_app(config, config_path=config_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        settings = await client.get("/api/config")
        assert settings.status_code == 200
        assert settings.json()["editable"]["download"]["request_interval_seconds"] == 3.0
        assert settings.json()["editable"]["backup_defaults"] == {
            "dry_run": False, "include_profile": True, "include_fancard": True,
        }
        assert settings.json()["writable"] is True

        denied = await client.patch("/api/config", json={"sync": {"max_posts_per_run": 30}})
        assert denied.status_code == 403

        invalid = await client.patch(
            "/api/config", json={"download": {"request_interval_seconds": 0.5}},
            headers={"X-Fanbox-Token": app.state.session_token},
        )
        assert invalid.status_code == 422

        saved = await client.patch(
            "/api/config",
            json={
                "sync": {"max_posts_per_run": 30},
                "backup_defaults": {
                    "dry_run": True, "include_profile": False, "include_fancard": True,
                },
                "logging": {"level": "debug"},
            },
            headers={"X-Fanbox-Token": app.state.session_token},
        )
        assert saved.status_code == 200
        assert saved.json()["editable"]["sync"]["max_posts_per_run"] == 30
        assert saved.json()["editable"]["logging"]["level"] == "DEBUG"
        assert saved.json()["editable"]["backup_defaults"]["dry_run"] is True
        assert saved.json()["editable"]["backup_defaults"]["include_profile"] is False
        reloaded = type(config).load(config_path)
        assert reloaded.sync.max_posts_per_run == 30
        assert reloaded.backup_defaults.dry_run is True
        assert reloaded.backup_defaults.include_profile is False
        assert reloaded.storage.database == config.storage.database


@pytest.mark.anyio
async def test_auth_endpoints_are_token_protected_and_never_return_secrets(tmp_path: Path):
    config, _ = dynamic_archive(tmp_path)
    app = create_app(config)

    class AuthService:
        def check(self):
            from fanbox_archiver.application import AuthStatus
            return AuthStatus("authenticated", "profile", "工作階段有效。", True, True)

        def logout(self):
            from fanbox_archiver.application import AuthStatus
            return AuthStatus("signed_out", "profile", "已登出。", True, False)

    class AuthJobs:
        def __init__(self): self.job = None
        def active(self): return self.job
        def start(self, **_kwargs):
            self.job = {"job_id": "auth-1", "status": "running", "error": None, "result": None}
            return self.job
        def get(self, job_id): return self.job if job_id == "auth-1" else None
        def cancel(self, job_id):
            if job_id != "auth-1": return None
            self.job = {**self.job, "status": "cancelling"}
            return self.job

    app.state.auth_service = AuthService()
    app.state.auth_jobs = AuthJobs()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied_status = await client.get("/api/auth/status")
        assert denied_status.status_code == 403
        status = await client.get(
            "/api/auth/status", headers={"X-Fanbox-Token": app.state.session_token},
        )
        assert status.json()["state"] == "authenticated"
        assert "cookie" not in status.text.casefold()
        assert "profile_dir" not in status.text

        denied = await client.post("/api/auth/login", json={"timeout_seconds": 60})
        assert denied.status_code == 403
        started = await client.post(
            "/api/auth/login", json={"timeout_seconds": 60},
            headers={"X-Fanbox-Token": app.state.session_token},
        )
        assert started.status_code == 202
        assert started.json()["job_id"] == "auth-1"

        cancelled = await client.post(
            "/api/auth/login/auth-1/cancel",
            headers={"X-Fanbox-Token": app.state.session_token},
        )
        assert cancelled.json()["status"] == "cancelling"

        app.state.auth_jobs.job = None
        logged_out = await client.post(
            "/api/auth/logout", headers={"X-Fanbox-Token": app.state.session_token},
        )
        assert logged_out.json()["state"] == "signed_out"


@pytest.mark.anyio
async def test_verify_job_endpoint_requires_token(tmp_path: Path):
    config, _ = dynamic_archive(tmp_path)
    app = create_app(config)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post("/api/jobs/verify")
        assert denied.status_code == 403
        accepted = await client.post(
            "/api/jobs/verify", headers={"X-Fanbox-Token": app.state.session_token},
        )
        assert accepted.status_code == 202
        assert accepted.json()["kind"] == "verify"
        app.state.jobs.wait(accepted.json()["job_id"])


@pytest.mark.anyio
async def test_every_api_time_point_carries_an_explicit_offset(tmp_path: Path):
    import re
    from datetime import datetime, timedelta, timezone

    from fanbox_archiver.config import AppConfig, StorageConfig
    from fanbox_archiver.models import ContentBlock, CreatorProfile, Post
    from fanbox_archiver.service import ArchiveService

    jst = timezone(timedelta(hours=9))
    config = AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "FANBOX", database=tmp_path / "FANBOX" / "backup.db",
    ))
    archive = ArchiveService(config)
    for number in (1, 2):
        archive.save(Post(
            post_id="123", creator_id="alice", creator_name="Alice", title=f"v{number}",
            published_at=datetime(2026, 11, 3, 0, 30, tzinfo=jst),
            updated_at=datetime(2026, 11, 3, number, tzinfo=jst),
            url="https://www.fanbox.cc/@alice/posts/123",
            blocks=[ContentBlock(type="paragraph", text=f"v{number}")], content_fingerprint=f"f{number}",
        ))
    profile = CreatorProfile(creator_id="alice", name="Alice", fanbox_url="https://www.fanbox.cc/@alice")
    profile.content_fingerprint = profile.calculate_fingerprint()
    archive.save_profile(profile)
    archive.db.record_supporting_creators([("alice", "Alice")])
    archive.save_fancard({"body": {
        "plan": {"creatorId": "alice", "title": "Gold", "fee": 100, "user": {"name": "Alice"}},
        "supportStartDatetime": "2026-09-01T00:00:00+09:00",
        "supportTransactions": [{"targetMonth": "2026-10"}],
    }}, b"jpeg", "image/jpeg", captured_at="2026-10-15T03:00:00+00:00")

    app = create_app(config)
    instant = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
    offset = re.compile(r"(?:Z|[+-]\d{2}:\d{2})$")
    naive: list[str] = []
    seen: list[str] = []

    def walk(value, where: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{where}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{where}[{index}]")
        elif isinstance(value, str) and instant.match(value):
            seen.append(where)
            if not offset.search(value):
                naive.append(where)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        submitted = await client.post(
            "/api/jobs/verify", headers={"X-Fanbox-Token": app.state.session_token},
        )
        assert submitted.status_code == 202
        job_id = submitted.json()["job_id"]
        app.state.jobs.wait(job_id)
        routes = [
            "/api/status", "/api/config", "/api/creators", "/api/creators/alice",
            "/api/creators/alice/profile", "/api/creators/alice/profile/versions",
            "/api/fancards", "/api/fancards/alice/2026-10", "/api/posts", "/api/posts/123",
            "/api/posts/123?version=1", "/api/jobs", f"/api/jobs/{job_id}",
        ]
        checked = 0
        for route in routes:
            response = await client.get(route)
            assert response.status_code == 200, route
            before = len(naive)
            walk(response.json(), route)
            checked += 1
            assert len(naive) == before, naive
    app.state.jobs.close()
    assert checked == len(routes) and naive == []
    assert len(seen) >= 20 and any(".events[" in where for where in seen)
    assert any("captured_at" in where for where in seen)


@pytest.mark.anyio
async def test_auth_status_reports_locked_not_error_while_a_job_runs(tmp_path: Path, monkeypatch):
    config, _ = dynamic_archive(tmp_path)
    app = create_app(config)
    checks = []

    class AuthService:
        def check(self):
            from fanbox_archiver.application import AuthStatus
            checks.append(1)
            return AuthStatus("authenticated", "profile", "工作階段有效。", True, True)

    app.state.auth_service = AuthService()
    token = {"X-Fanbox-Token": app.state.session_token}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.get("/api/auth/status", headers=token)
        assert first.json()["state"] == "authenticated"
        assert first.json()["last_known"] is None

        monkeypatch.setattr(app.state.jobs, "has_active", lambda: True)
        locked = (await client.get("/api/auth/status", headers=token)).json()
        assert locked["state"] == "locked"
        assert locked["can_login"] is False and locked["can_logout"] is False
        assert locked["last_known"]["state"] == "authenticated"
        assert locked["last_known"]["checked_at"].endswith("+00:00")
        assert set(locked["last_known"]) == {"state", "checked_at"}
        assert len(checks) == 1  # the profile is never opened while a job holds it
        login = await client.post("/api/auth/login", json={"timeout_seconds": 60}, headers=token)
        logout = await client.post("/api/auth/logout", headers=token)
        assert login.status_code == 409 and logout.status_code == 409

        monkeypatch.setattr(app.state.jobs, "has_active", lambda: False)
        recovered = (await client.get("/api/auth/status", headers=token)).json()
        assert recovered["state"] == "authenticated"
        assert len(checks) == 2


@pytest.mark.anyio
async def test_list_endpoints_page_and_sort_with_validated_parameters(tmp_path: Path):
    config, _ = dynamic_archive(tmp_path)
    app = create_app(config)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        jobs = (await client.get("/api/jobs?kind=backup&order=asc&page=3")).json()
        assert set(jobs) == {"items", "page", "pages", "page_size", "total", "active"}
        assert (jobs["page"], jobs["page_size"], jobs["active"]) == (1, 20, None)
        for bad in ("kind=other", "order=sideways", "status=unknown", "page_size=101", "page=0"):
            assert (await client.get(f"/api/jobs?{bad}")).status_code == 422
        posts = (await client.get("/api/posts")).json()
        assert posts["page_size"] == 20
        assert (await client.get("/api/posts?order=asc")).status_code == 200
        assert (await client.get("/api/posts?order=up")).status_code == 422
        assert (await client.get("/api/posts/123?order=asc")).status_code == 200
    app.state.jobs.close()


@pytest.mark.anyio
async def test_diagnostics_report_versions_and_paths_without_credentials(tmp_path: Path, monkeypatch):
    import fanbox_archiver.diagnostics as diagnostics
    from fanbox_archiver import __version__
    from fanbox_archiver.database import SCHEMA_VERSION

    monkeypatch.setenv("FANBOX_COOKIE", "FANBOXSESSID=secret-cookie-value")
    monkeypatch.delenv("FANBOX_ARCHIVER_DESKTOP_EXE", raising=False)
    config, _ = dynamic_archive(tmp_path)
    app = create_app(config, config_path=tmp_path / "config.yaml")
    token = {"X-Fanbox-Token": app.state.session_token}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/diagnostics")).status_code == 403
        response = await client.get("/api/diagnostics", headers=token)

    assert response.status_code == 200
    info = response.json()
    assert info["app_version"] == __version__
    assert (info["mode"], info["desktop_version"]) == ("browser", None)
    assert info["schema"] == {"database": SCHEMA_VERSION, "supported": SCHEMA_VERSION}
    assert info["paths"]["archive"] == str(config.storage.output_dir.resolve())
    assert info["paths"]["archive_logs"] == str((config.storage.output_dir / "logs").resolve())
    assert info["paths"]["desktop_logs"] is None and info["folders"]["desktop_logs"] is False
    assert f"程式版本：{__version__}" in info["text"] and "瀏覽器版" in info["text"]
    serialized = response.text
    assert "secret-cookie-value" not in serialized and app.state.session_token not in serialized
    assert diagnostics.diagnostics_text(info) == info["text"]


@pytest.mark.anyio
async def test_diagnostics_desktop_mode_reports_shell_version_and_log_folder(tmp_path: Path, monkeypatch):
    desktop_logs = tmp_path / "desktop-logs"
    desktop_logs.mkdir()
    monkeypatch.setenv("FANBOX_ARCHIVER_DESKTOP_EXE", str(tmp_path / "FANBOX Archiver.exe"))
    monkeypatch.setenv("FANBOX_ARCHIVER_DESKTOP_VERSION", "9.9.9-alpha")
    monkeypatch.setenv("FANBOX_ARCHIVER_DESKTOP_LOG_DIR", str(desktop_logs))
    config, _ = dynamic_archive(tmp_path)
    app = create_app(config)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        info = (await client.get("/api/diagnostics",
                                 headers={"X-Fanbox-Token": app.state.session_token})).json()

    assert (info["mode"], info["desktop_version"]) == ("desktop", "9.9.9-alpha")
    assert info["paths"]["desktop_logs"] == str(desktop_logs.resolve())
    assert info["folders"]["desktop_logs"] is True
    assert "桌面版 9.9.9-alpha" in info["text"] and "桌面日誌：" in info["text"]


@pytest.mark.anyio
async def test_open_folder_accepts_only_fixed_targets_with_token(tmp_path: Path, monkeypatch):
    import fanbox_archiver.diagnostics as diagnostics

    opened: list[Path] = []
    monkeypatch.setattr(diagnostics, "open_folder", opened.append)
    monkeypatch.setattr(diagnostics, "can_open_folders", lambda: True)
    monkeypatch.delenv("FANBOX_ARCHIVER_DESKTOP_LOG_DIR", raising=False)
    config, _ = dynamic_archive(tmp_path)
    app = create_app(config)
    token = {"X-Fanbox-Token": app.state.session_token}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/api/diagnostics/open", json={"target": "archive"})).status_code == 403
        unknown = await client.post("/api/diagnostics/open", headers=token, json={"target": "profile"})
        assert unknown.status_code == 422
        smuggled = await client.post("/api/diagnostics/open", headers=token,
                                     json={"target": "archive", "path": str(tmp_path)})
        assert smuggled.status_code == 422
        assert (await client.post("/api/diagnostics/open", headers=token,
                                  json={"target": "desktop_logs"})).status_code == 404
        logs = config.storage.output_dir / "logs"
        if logs.exists():
            import shutil

            shutil.rmtree(logs)
        missing = await client.post("/api/diagnostics/open", headers=token, json={"target": "archive_logs"})
        assert missing.status_code == 404
        assert opened == []

        response = await client.post("/api/diagnostics/open", headers=token, json={"target": "archive"})

    assert response.json() == {"opened": "archive"}
    assert opened == [config.storage.output_dir.resolve()]


@pytest.mark.anyio
async def test_theme_setting_is_saved_and_rendered_into_the_page(tmp_path: Path):
    config, _ = dynamic_archive(tmp_path)
    config_path = tmp_path / "config.yaml"
    type(config).save_editable(config_path, config, {})
    app = create_app(config, config_path=config_path)
    token = {"X-Fanbox-Token": app.state.session_token}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert '<html lang="zh-Hant" data-theme="auto">' in (await client.get("/")).text
        assert (await client.get("/api/config")).json()["editable"]["display"]["theme"] == "system"

        invalid = await client.patch("/api/config", headers=token, json={"display": {"theme": "sepia"}})
        assert invalid.status_code == 422
        saved = await client.patch("/api/config", headers=token, json={"display": {"theme": "dark"}})
        assert saved.status_code == 200
        assert saved.json()["editable"]["display"]["theme"] == "dark"
        assert saved.json()["editable"]["display"]["timezone"] == config.display.timezone
        assert '<html lang="zh-Hant" data-theme="dark">' in (await client.get("/")).text

    assert type(config).load(config_path).display.theme == "dark"


@pytest.mark.anyio
async def test_custom_colors_are_validated_saved_and_served_as_css(tmp_path: Path):
    config, _ = dynamic_archive(tmp_path)
    config_path = tmp_path / "config.yaml"
    type(config).save_editable(config_path, config, {})
    app = create_app(config, config_path=config_path)
    token = {"X-Fanbox-Token": app.state.session_token}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        home = (await client.get("/")).text
        assert '<link id="custom-theme" rel="stylesheet" href="/theme.css">' in home
        settings = (await client.get("/api/config")).json()
        assert settings["theme_colors"]["keys"][:2] == ["bg", "surface"]
        assert settings["theme_colors"]["defaults"]["dark"]["accent"] == "#ff983f"
        empty = await client.get("/theme.css")
        assert empty.headers["content-type"].startswith("text/css") and "--" not in empty.text

        rejected = await client.patch("/api/config", headers=token, json={"display": {"colors": {
            "light": {"accent": "#000000;}*{background:url(https://example.test)"}, "dark": {}}}})
        assert rejected.status_code == 422
        saved = await client.patch("/api/config", headers=token, json={"display": {"colors": {
            "light": {"accent": "#0055AA"}, "dark": {"bg": "#000000"}}}})
        assert saved.status_code == 200
        css = (await client.get("/theme.css")).text

    assert ':root[data-theme="light"]{--accent:#0055aa;}' in css
    assert ':root[data-theme="dark"]{--bg:#000000;}' in css
    reloaded = type(config).load(config_path).display.colors
    assert (reloaded.light, reloaded.dark) == ({"accent": "#0055aa"}, {"bg": "#000000"})
