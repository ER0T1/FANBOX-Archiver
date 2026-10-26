import json
import sqlite3
from datetime import datetime
from pathlib import Path

from fanbox_archiver.config import AppConfig, StorageConfig
from fanbox_archiver.models import Asset, AssetStatus, ContentBlock, Post, PostStatus
from fanbox_archiver.parser import fingerprint
from fanbox_archiver.service import ArchiveService
from fanbox_archiver.database import Database, SCHEMA_VERSION
from fanbox_archiver.downloader import DownloadError, sha256_file


def configured(tmp_path: Path) -> AppConfig:
    return AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "backup",
        database=tmp_path / "backup" / "backup.db",
    ))


def make_post(title: str, text: str = "body") -> Post:
    post = Post(
        post_id="42", creator_id="alice", creator_name="Alice", title=title,
        published_at=datetime(2026, 1, 2), updated_at=datetime(2026, 1, 3),
        url="https://www.fanbox.cc/@alice/posts/42",
        blocks=[ContentBlock(type="paragraph", text=text)],
    )
    post.content_fingerprint = fingerprint(post)
    return post


def test_changed_post_creates_independent_versions_and_latest_alias(tmp_path: Path):
    service = ArchiveService(configured(tmp_path))
    first = make_post("first")
    assert service.save(first) == PostStatus.COMPLETED
    second = make_post("second")
    assert service.save(second) == PostStatus.COMPLETED

    root = service.storage.post_dir(second)
    assert "# first" in (root / "versions/v0001/post.md").read_text(encoding="utf-8")
    assert "# second" in (root / "versions/v0002/post.md").read_text(encoding="utf-8")
    latest = (root / "post.md").read_text(encoding="utf-8")
    assert "archive_version: 2" in latest
    assert "versions/v0001/post.md" in latest
    assert "../v0002/post.md" in (root / "versions/v0001/post.md").read_text(encoding="utf-8")
    assert len(service.db.version_rows("42")) == 2
    assert service.verify() == []


def test_identical_content_does_not_create_another_version(tmp_path: Path):
    service = ArchiveService(configured(tmp_path))
    post = make_post("same")
    service.save(post)
    service.save(make_post("same"))
    assert [row["version_number"] for row in service.db.version_rows("42")] == [1]


def test_manifest_detects_historical_tampering(tmp_path: Path):
    service = ArchiveService(configured(tmp_path))
    post = make_post("first")
    service.save(post)
    version_json = service.storage.version_dir(post, 1) / "post.json"
    version_json.write_text("{}", encoding="utf-8")
    issues = service.verify()
    assert any("歷史版本 SHA-256" in issue.reason for issue in issues)


def test_existing_completed_post_is_registered_as_v0001(tmp_path: Path):
    config = configured(tmp_path)
    service = ArchiveService(config)
    post = make_post("legacy")
    root = service.storage.prepare(post)
    service.storage.assign_asset_paths(post)
    service.storage.write_post_json(post)
    service.storage.atomic_write_text(root / "post.md", "# legacy\n")
    service.db.upsert_post(post, str(root), PostStatus.COMPLETED)

    migrated = ArchiveService(config)
    rows = migrated.db.version_rows("42")
    assert len(rows) == 1
    assert Path(rows[0]["local_path"]).joinpath("manifest.json").exists()
    assert config.storage.database.with_name(
        f"backup.db.pre-v{SCHEMA_VERSION}.bak"
    ).exists() is False


def test_verify_reports_completed_post_without_version(tmp_path: Path):
    service = ArchiveService(configured(tmp_path))
    post = make_post("missing version")
    missing_root = tmp_path / "missing"
    service.db.upsert_post(post, str(missing_root), PostStatus.COMPLETED)
    issues = service.verify()
    assert any(issue.post_id == "42" and "缺少完成版本" in issue.reason for issue in issues)


def test_failed_latest_alias_update_keeps_previous_version_current(tmp_path: Path, monkeypatch):
    service = ArchiveService(configured(tmp_path))
    first = make_post("first")
    service.save(first)
    root = service.storage.post_dir(first)

    def fail_alias(*args, **kwargs):
        raise OSError("simulated alias failure")

    monkeypatch.setattr(service.storage, "update_latest_alias", fail_alias)
    try:
        service.save(make_post("second"))
    except OSError:
        pass
    else:
        raise AssertionError("expected alias failure")
    assert "# first" in (root / "post.md").read_text(encoding="utf-8")
    assert service.db.latest_version("42", completed_only=True)["version_number"] == 1


def test_schema_migration_backs_up_existing_database_once(tmp_path: Path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE creators(creator_id TEXT PRIMARY KEY,name TEXT NOT NULL,url TEXT,last_checked_at TEXT)")
        db.execute("CREATE TABLE posts(post_id TEXT PRIMARY KEY,creator_id TEXT,title TEXT,published_at TEXT,updated_at TEXT,status TEXT,local_path TEXT,content_fingerprint TEXT,last_error TEXT,last_checked_at TEXT)")
        db.execute("CREATE TABLE assets(id INTEGER PRIMARY KEY,asset_id TEXT,post_id TEXT,type TEXT,source_url TEXT,original_name TEXT,local_path TEXT,size INTEGER,sha256 TEXT,etag TEXT,last_modified TEXT,status TEXT,error TEXT)")
        db.execute("CREATE TABLE backup_runs(run_id INTEGER PRIMARY KEY,started_at TEXT,finished_at TEXT,scope TEXT,success_count INTEGER DEFAULT 0,failure_count INTEGER DEFAULT 0)")
    Database(path)
    backup = path.with_name(f"legacy.db.pre-v{SCHEMA_VERSION}.bak")
    assert backup.exists()
    first_mtime = backup.stat().st_mtime_ns
    Database(path)
    assert backup.stat().st_mtime_ns == first_mtime


def test_partial_retry_finishes_same_version_before_switching_latest(tmp_path: Path, monkeypatch):
    import fanbox_archiver.service as service_module

    service = ArchiveService(configured(tmp_path))
    first = make_post("first")
    service.save(first)
    changed = make_post("second")
    changed.assets = [Asset(
        asset_id="file", type="file",
        url="https://downloads.fanbox.cc/files/post/42/file.bin",
        original_name="file.bin",
    )]
    changed.content_fingerprint = fingerprint(changed)

    class FakeDownloader:
        succeeds = False

        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def download(self, asset, target):
            target.parent.mkdir(parents=True, exist_ok=True)
            if not self.succeeds:
                target.with_name(target.name + ".part").write_bytes(b"partial")
                asset.status = AssetStatus.FAILED
                raise DownloadError("simulated")
            target.write_bytes(b"complete")
            asset.status = AssetStatus.COMPLETED
            asset.size = target.stat().st_size
            asset.sha256 = sha256_file(target)

    monkeypatch.setattr(service_module, "AssetDownloader", FakeDownloader)
    assert service.save(changed) == PostStatus.PARTIAL
    assert service.db.latest_version("42", completed_only=True)["version_number"] == 1
    assert len(service.db.version_rows("42")) == 2

    retry_row = service.db.retryable_versions()[0]
    retry_post = Post.model_validate_json(Path(retry_row["json_path"]).read_text(encoding="utf-8"))
    assert retry_post.title == "second"

    FakeDownloader.succeeds = True
    assert service.save(retry_post, force=True) == PostStatus.COMPLETED
    assert service.db.latest_version("42", completed_only=True)["version_number"] == 2
    assert len(service.db.version_rows("42")) == 2
