from pathlib import Path
from datetime import timedelta, timezone

from typer.testing import CliRunner
import pytest

import fanbox_archiver.cli as cli
from fanbox_archiver.config import AppConfig, StorageConfig
from fanbox_archiver.models import Post, PostStatus
from fanbox_archiver.service import ArchiveService


runner = CliRunner()


@pytest.fixture
def configured_cli(monkeypatch, tmp_path: Path) -> AppConfig:
    config = AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "out", database=tmp_path / "out/db.sqlite"
    ))
    monkeypatch.setattr(cli, "load_config", lambda path: config)
    return config


def test_format_local_time_converts_utc_without_changing_storage():
    taipei = timezone(timedelta(hours=8))
    assert cli.format_local_time("2026-10-26T07:43:33+00:00", taipei) == "2026-10-26T15:43:33+08:00"


def test_backup_normalizes_multiple_creators_and_forwards_options(monkeypatch, configured_cli):
    captured = {}

    def fake_run(settings, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli, "_run_backup", fake_run)
    result = runner.invoke(cli.app, [
        "backup", "--creator", "https://www.fanbox.cc/@alice",
        "--creator", "https://bob.fanbox.cc", "--profile", "--fancard",
        "--dry-run", "--max-posts", "3",
    ])
    assert result.exit_code == 0
    assert captured["creators"] == ("alice", "bob")
    assert captured["posts"] == ()
    assert captured["dry_run"] is True
    assert captured["max_posts"] == 3
    assert captured["scope"] == "creators:alice,bob"
    assert captured["include_profile"] is True
    assert captured["include_fancard"] is True


def test_backup_normalizes_multiple_posts(monkeypatch, configured_cli):
    captured = {}
    monkeypatch.setattr(cli, "_run_backup", lambda settings, **kwargs: captured.update(kwargs))
    result = runner.invoke(cli.app, [
        "backup", "--post", "123",
        "--post", "https://alice.fanbox.cc/posts/456", "--dry-run",
    ])
    assert result.exit_code == 0
    assert captured["creators"] == ()
    assert captured["posts"] == ("123", "456")
    assert captured["dry_run"] is True
    assert captured["scope"] == "posts:123,456"


def test_backup_rejects_mutually_exclusive_and_dependent_options(configured_cli):
    mixed = runner.invoke(cli.app, ["backup", "--creator", "alice", "--post", "123"])
    assert mixed.exit_code == 2
    assert "不可同時使用" in mixed.output
    missing_creator = runner.invoke(cli.app, ["backup", "--profile"])
    assert missing_creator.exit_code == 2
    assert "只能搭配 --creator" in missing_creator.output


def test_removed_download_and_sync_commands_are_absent_from_help():
    help_result = runner.invoke(cli.app, ["--help"])
    assert help_result.exit_code == 0
    assert " download " not in help_result.output
    assert " sync " not in help_result.output
    assert runner.invoke(cli.app, ["download", "123"]).exit_code != 0
    assert runner.invoke(cli.app, ["sync", "--supporting"]).exit_code != 0


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


def test_invalid_creator_input_returns_nonzero(configured_cli):
    result = runner.invoke(cli.app, ["backup", "--creator", "https://www.fanbox.cc/not-a-creator"])
    assert result.exit_code == 2
    assert "格式錯誤" in result.output
