from pathlib import Path
from datetime import timedelta, timezone

from typer.testing import CliRunner

import fanbox_archiver.cli as cli
from fanbox_archiver.config import AppConfig, StorageConfig
from fanbox_archiver.models import Post, PostStatus
from fanbox_archiver.service import ArchiveService


runner = CliRunner()


def test_format_local_time_converts_utc_without_changing_storage():
    taipei = timezone(timedelta(hours=8))
    assert cli.format_local_time("2026-10-26T07:43:33+00:00", taipei) == "2026-10-26T15:43:33+08:00"


def test_backup_normalizes_creator_url_and_forwards_options(monkeypatch, tmp_path: Path):
    captured = {}
    config = AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "out", database=tmp_path / "out/db.sqlite"
    ))
    monkeypatch.setattr(cli, "load_config", lambda path: config)

    def fake_run(settings, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli, "_run_backup", fake_run)
    result = runner.invoke(cli.app, [
        "backup", "--creator", "https://www.fanbox.cc/@alice/posts/123",
        "--dry-run", "--max-posts", "3",
    ])
    assert result.exit_code == 0
    assert captured["creator"] == "alice"
    assert captured["dry_run"] is True
    assert captured["max_posts"] == 3
    assert captured["scope"] == "creator:alice"


def test_sync_compatibility_command_uses_shared_backup_runner(monkeypatch, tmp_path: Path):
    captured = {}
    config = AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "out", database=tmp_path / "out/db.sqlite"
    ))
    monkeypatch.setattr(cli, "load_config", lambda path: config)
    monkeypatch.setattr(cli, "_run_backup", lambda settings, **kwargs: captured.update(kwargs))
    result = runner.invoke(cli.app, ["sync", "--supporting", "--dry-run"])
    assert result.exit_code == 0
    assert captured["creator"] is None
    assert captured["dry_run"] is True
    assert captured["scope"] == "supporting"


def test_creator_listing_includes_local_count_and_sync_status(tmp_path: Path):
    config = AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "out", database=tmp_path / "out/db.sqlite"
    ))
    service = ArchiveService(config)
    service.db.record_supporting_creators([("alice", "Alice")])
    post = Post(
        post_id="1", creator_id="alice", creator_name="Alice", title="one",
        url="https://www.fanbox.cc/@alice/posts/1", content_fingerprint="fingerprint",
    )
    service.db.upsert_post(post, str(tmp_path / "post"), PostStatus.COMPLETED)
    service.db.update_creator_sync("alice", recent_checked=True, backfill_completed=True, success=True)
    row = service.db.creator_listing()[0]
    assert row["post_count"] == 1
    assert row["completed_count"] == 1
    assert row["status"] == "同步完成"
    assert row["last_sync"]


def test_invalid_creator_input_returns_nonzero(monkeypatch, tmp_path: Path):
    config = AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "out", database=tmp_path / "out/db.sqlite"
    ))
    monkeypatch.setattr(cli, "load_config", lambda path: config)
    result = runner.invoke(cli.app, ["backup", "--creator", "https://www.fanbox.cc/not-a-creator"])
    assert result.exit_code != 0
    assert "格式錯誤" in result.output
