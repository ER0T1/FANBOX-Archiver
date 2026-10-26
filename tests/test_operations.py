from pathlib import Path

from fanbox_archiver.config import AppConfig, DownloadConfig, LoggingConfig, StorageConfig
from fanbox_archiver.logging_setup import configure_logging
from fanbox_archiver.models import Post, PostStatus
from fanbox_archiver.service import ArchiveService


def settings(tmp_path: Path) -> AppConfig:
    return AppConfig(
        storage=StorageConfig(output_dir=tmp_path / "out", database=tmp_path / "out/db.sqlite"),
        logging=LoggingConfig(write_to_file=True, keep_days=7),
    )


def test_file_logging_redacts_credentials(tmp_path: Path):
    config = settings(tmp_path)
    logger = configure_logging(config)
    logger.error("Cookie: secret=value; other=hidden")
    logger.error("request?access_token=top-secret")
    for handler in logger.handlers:
        handler.flush()
    content = (config.storage.output_dir / "logs/fanbox-archiver.log").read_text(encoding="utf-8")
    assert "secret=value" not in content
    assert "top-secret" not in content
    assert "[REDACTED]" in content


def test_parallel_download_setting_remains_conservatively_disabled():
    try:
        DownloadConfig(max_concurrent=2)
    except ValueError:
        pass
    else:
        raise AssertionError("parallel downloads must remain disabled")


def test_operational_status_queries_report_failures_and_backfill(tmp_path: Path):
    service = ArchiveService(settings(tmp_path))
    service.db.record_supporting_creators([("alice", "Alice")])
    post = Post(
        post_id="7", creator_id="alice", creator_name="Alice", title="failed",
        url="https://www.fanbox.cc/@alice/posts/7", content_fingerprint="x",
    )
    service.db.upsert_post(post, str(tmp_path / "post"), PostStatus.FAILED)
    service.db.set_post_status("7", PostStatus.FAILED, "network error")
    service.db.update_creator_sync("alice", recent_checked=True, backfill_cursor="2", error="network error")
    run = service.db.begin_run("supporting")
    service.db.finish_run(run, 0, 1)
    assert service.db.latest_run()["failure_count"] == 1
    assert service.db.recent_failures()[0]["post_id"] == "7"
    assert service.db.incomplete_creator_rows()[0]["backfill_cursor"] == "2"


def test_dry_run_is_not_reported_as_successful_backup(tmp_path: Path):
    service = ArchiveService(settings(tmp_path))
    preview = service.db.begin_run("supporting", dry_run=True)
    service.db.finish_run(preview, 0, 0, discovered=10, new=10)
    assert service.db.latest_successful_run() is None
    backup = service.db.begin_run("supporting")
    service.db.finish_run(backup, 2, 0)
    assert service.db.latest_successful_run()["run_id"] == backup
