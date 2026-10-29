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

        post = await client.get("/api/posts/123")
        assert post.status_code == 200
        assert post.json()["version"] == 2
        assert post.json()["navigation"] == {
            "previous": None, "next": None, "position": 1, "total": 1,
        }
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
