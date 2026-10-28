from pathlib import Path

import fanbox_archiver.application.backup as backup_module
from fanbox_archiver.application import BackupRequest, BackupUseCase
from fanbox_archiver.application.events import CollectingEventSink
from fanbox_archiver.client import Creator, PostSummary
from fanbox_archiver.config import AppConfig, AuthConfig, StorageConfig
from fanbox_archiver.models import CreatorProfile


class DryRunClient:
    def __init__(self, **kwargs):
        self.options = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def supporting_creators(self):
        return [Creator("alice", "Alice")]

    def creator_post_pages(self, creator_id):
        return [f"https://api.fanbox.cc/{creator_id}/0"]

    def creator_page(self, page_url):
        return [PostSummary("123", title="example")]


def test_dry_run_use_case_emits_serializable_events_and_records_run(monkeypatch, tmp_path: Path):
    config = AppConfig(
        auth=AuthConfig(profile_dir=tmp_path / "profile"),
        storage=StorageConfig(
            output_dir=tmp_path / "out", database=tmp_path / "out" / "backup.db"
        ),
    )
    sink = CollectingEventSink()
    monkeypatch.setattr(backup_module, "FanboxClient", DryRunClient)
    monkeypatch.setattr(backup_module, "cookie_header", lambda *args, **kwargs: "cookie=value")

    outcome = BackupUseCase(config, sink=sink).run(BackupRequest(dry_run=True))

    assert outcome.dry_run is True
    assert outcome.plan.new == 1
    assert [event.kind for event in sink.events] == [
        "job_started", "plan_ready", "job_finished",
    ]
    assert sink.events[1].model_dump()["data"]["selected"] == 1
    assert sink.events[1].model_dump()["data"]["creators"] == 1
    assert sink.events[1].model_dump()["data"]["creator_ids"] == ["alice"]
    run = backup_module.ArchiveService(config).db.latest_run()
    assert run["dry_run"] == 1
    assert run["new_count"] == 1
    assert run["failure_count"] == 0


def test_cancelled_use_case_stops_before_network_client(monkeypatch, tmp_path: Path):
    from fanbox_archiver.application import BackupCancelled, CancellationToken

    config = AppConfig(
        auth=AuthConfig(profile_dir=tmp_path / "profile"),
        storage=StorageConfig(
            output_dir=tmp_path / "out", database=tmp_path / "out" / "backup.db"
        ),
    )
    token = CancellationToken()
    token.cancel()
    monkeypatch.setattr(backup_module, "cookie_header", lambda *args, **kwargs: "cookie=value")

    try:
        BackupUseCase(config, cancellation=token).run(BackupRequest(dry_run=True))
    except BackupCancelled:
        pass
    else:
        raise AssertionError("expected BackupCancelled")

    assert backup_module.ArchiveService(config).db.latest_run() is None


def test_dry_run_profiles_are_planned_without_writes(monkeypatch, tmp_path: Path):
    class ProfileClient(DryRunClient):
        def creator_profile(self, creator_id):
            item = CreatorProfile(
                creator_id=creator_id, name="Alice", description="Preview",
                fanbox_url=f"https://www.fanbox.cc/@{creator_id}",
            )
            item.content_fingerprint = item.calculate_fingerprint()
            return item

    config = AppConfig(
        auth=AuthConfig(profile_dir=tmp_path / "profile"),
        storage=StorageConfig(
            output_dir=tmp_path / "out", database=tmp_path / "out" / "backup.db"
        ),
    )
    sink = CollectingEventSink()
    monkeypatch.setattr(backup_module, "FanboxClient", ProfileClient)
    monkeypatch.setattr(backup_module, "cookie_header", lambda *args, **kwargs: "cookie=value")

    BackupUseCase(config, sink=sink).run(BackupRequest(dry_run=True))

    assert [event.kind for event in sink.events] == [
        "job_started", "profile_started", "profile_finished", "plan_ready", "job_finished",
    ]
    finished = sink.events[2].data
    assert finished["status"] == "new" and finished["dry_run"] is True
    assert sink.events[3].data["scans"][0]["profile"] == "new"
    archive = backup_module.ArchiveService(config)
    assert archive.db.profile_versions("alice") == []
    assert not (config.storage.output_dir / "alice" / "profile").exists()


def test_profile_only_mode_skips_post_scan_and_saves_profile(monkeypatch, tmp_path: Path):
    class ProfileOnlyClient(DryRunClient):
        def creator_post_pages(self, creator_id):
            raise AssertionError("profile-only mode must not scan posts")

        def creator_profile(self, creator_id):
            item = CreatorProfile(
                creator_id=creator_id, name="Alice", description="Profile only",
                fanbox_url=f"https://www.fanbox.cc/@{creator_id}",
            )
            item.content_fingerprint = item.calculate_fingerprint()
            return item

    config = AppConfig(
        auth=AuthConfig(profile_dir=tmp_path / "profile"),
        storage=StorageConfig(
            output_dir=tmp_path / "out", database=tmp_path / "out" / "backup.db"
        ),
    )
    sink = CollectingEventSink()
    monkeypatch.setattr(backup_module, "FanboxClient", ProfileOnlyClient)
    monkeypatch.setattr(backup_module, "cookie_header", lambda *args, **kwargs: "cookie=value")

    outcome = BackupUseCase(config, sink=sink).run(BackupRequest(mode="profile"))

    assert outcome.plan.selected == []
    assert [event.kind for event in sink.events] == [
        "job_started", "profile_started", "profile_finished", "plan_ready", "job_finished",
    ]
    assert backup_module.ArchiveService(config).db.latest_profile_version("alice") is not None


def test_fancard_only_mode_skips_posts_and_saves_card(monkeypatch, tmp_path: Path):
    class FancardOnlyClient(DryRunClient):
        def creator_post_pages(self, creator_id):
            raise AssertionError("fancard-only mode must not scan posts")

    class FancardSession:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def fetch_fancard(self, creator_id):
            return {"body": {
                "plan": {"creatorId": creator_id, "title": "Gold", "user": {"name": "Alice"}},
                "supportTransactions": [{"targetMonth": "2026-10"}],
                "supporterCardImageUrl": "",
            }}

    config = AppConfig(
        auth=AuthConfig(profile_dir=tmp_path / "profile"),
        storage=StorageConfig(
            output_dir=tmp_path / "out", database=tmp_path / "out" / "backup.db"
        ),
    )
    sink = CollectingEventSink()
    monkeypatch.setattr(backup_module, "FanboxClient", FancardOnlyClient)
    monkeypatch.setattr(backup_module, "BrowserPostSession", FancardSession)
    monkeypatch.setattr(
        BackupUseCase, "_auth_material", lambda self, browser: (True, "cookie=value", None)
    )

    outcome = BackupUseCase(config, sink=sink).run(BackupRequest(mode="fancard"))

    assert outcome.plan.selected == []
    assert any(event.kind == "fancard_finished" for event in sink.events)
    row = backup_module.ArchiveService(config).db.latest_fancard_version("alice", "2026-10")
    assert row is not None
