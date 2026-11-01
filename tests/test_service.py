from datetime import datetime
from pathlib import Path

from fanbox_archiver.config import AppConfig, StorageConfig
from fanbox_archiver.models import Asset, ContentBlock, Post, PostStatus
from fanbox_archiver.service import ArchiveService


def test_metadata_only_backup_is_pending_and_verify_reports_it(tmp_path: Path):
    config = AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "backup",
        database=tmp_path / "backup" / "backup.db",
    ))
    post = Post(
        post_id="1", creator_id="creator", creator_name="作者", title="標題",
        published_at=datetime(2026, 1, 2), url="https://www.fanbox.cc/@creator/posts/1",
        assets=[Asset(
            asset_id="a", type="image",
            url="https://downloads.fanbox.cc/images/post/1/a.png",
            original_name="a.png",
        )],
        blocks=[ContentBlock(type="image", asset_id="a")],
    )
    service = ArchiveService(config)
    assert service.save(post, download_assets=False) == PostStatus.PENDING
    issues = service.verify()
    assert len(issues) == 1
    assert "尚未完成" in issues[0].reason


def test_creator_avatar_is_saved_and_registered(tmp_path: Path):
    config = AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "backup",
        database=tmp_path / "backup" / "backup.db",
    ))
    service = ArchiveService(config)
    service.db.record_supporting_creators([("creator", "作者")])
    post = Post(
        post_id="2", creator_id="creator", creator_name="作者", title="標題",
        creator_icon_url="https://pixiv.pximg.net/icon.jpeg",
        url="https://www.fanbox.cc/@creator/posts/2",
    )

    class FakeDownloader:
        def download(self, asset, target):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"avatar")
            asset.sha256 = "avatar-sha256"
            return asset

    service._save_creator_icon(post, FakeDownloader())
    row = service.db.creator_row("creator")
    assert row["icon_url"] == post.creator_icon_url
    assert row["icon_sha256"] == "avatar-sha256"
    assert Path(row["icon_path"]).read_bytes() == b"avatar"


def test_verify_reports_indeterminate_scan_then_monotonic_safe_progress(tmp_path: Path):
    config = AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "backup",
        database=tmp_path / "backup" / "backup.db",
    ))
    metadata = config.storage.output_dir / "creator" / "123" / "post.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("not-json", encoding="utf-8")
    progress: list[dict[str, object]] = []

    issues = ArchiveService(config).verify(progress.append)

    assert len(issues) == 1
    assert progress[0]["phase"] == "scan" and progress[0]["total"] is None
    assert progress[-1] == {
        "phase": "posts", "current": 1, "total": 1, "percent": 100.0,
        "item": "Post 123", "issue_count": 1,
    }
    assert [int(item["current"]) for item in progress] == sorted(
        int(item["current"]) for item in progress
    )
    assert all(str(tmp_path) not in str(item["item"]) for item in progress)
