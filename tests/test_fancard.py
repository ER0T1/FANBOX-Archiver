import json
from datetime import datetime
from pathlib import Path

from fanbox_archiver.config import AppConfig, StorageConfig
from fanbox_archiver.models import ContentBlock, Post
from fanbox_archiver.service import ArchiveService


def service(tmp_path: Path) -> ArchiveService:
    config = AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "out", database=tmp_path / "out/db.sqlite"
    ))
    result = ArchiveService(config)
    result.db.record_supporting_creators([("alice", "Alice")])
    return result


def payload(description: str = "Password: example") -> dict:
    return {"body": {
        "plan": {
            "id": "plan-1", "title": "Gold", "fee": 1000,
            "description": description, "coverImageUrl": "https://pixiv.pximg.net/card.jpeg",
            "user": {"userId": "u1", "name": "Alice", "iconUrl": "https://pixiv.pximg.net/icon.jpeg"},
            "creatorId": "alice", "hasAdultContent": False,
            "paymentMethod": "card", "perks": ["downloads"],
        },
        "supportStartDatetime": "2026-10-01T00:00:00+09:00",
        "supportTransactions": [{
            "id": "tx1", "supporter": {"userId": "me", "name": "Me", "iconUrl": None},
            "paidAmount": 1000, "transactionDatetime": "2026-10-01T00:00:00+09:00",
            "targetMonth": "2026-10",
        }],
        "supportReservations": [],
        "supporterCardImageUrl": "https://pixiv.pximg.net/card.jpeg",
    }}


def test_fancard_is_saved_by_month_with_readable_metadata(tmp_path: Path):
    archive = service(tmp_path)
    status, version = archive.save_fancard(payload(), b"jpeg-data", "image/jpeg")
    assert status == "new"
    assert version.name == "v0001"
    markdown = (version / "fancard.md").read_text(encoding="utf-8")
    assert "Password: example" in markdown
    assert "2026-10" in markdown
    assert (version / "card.jpeg").read_bytes() == b"jpeg-data"
    month_root = version.parent.parent
    assert (month_root / "fancard.json").read_bytes() == (version / "fancard.json").read_bytes()
    assert (month_root / "fancard.md").read_bytes() == (version / "fancard.md").read_bytes()
    assert archive.verify() == []


def test_fancard_unchanged_is_not_duplicated_and_change_creates_version(tmp_path: Path):
    archive = service(tmp_path)
    first_status, _ = archive.save_fancard(payload(), b"one", "image/jpeg")
    same_status, _ = archive.save_fancard(payload(), b"one", "image/jpeg")
    changed_status, changed = archive.save_fancard(payload("new password"), b"two", "image/jpeg")
    assert (first_status, same_status, changed_status) == ("new", "unchanged", "updated")
    assert changed.name == "v0002"
    with archive.db.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM fancard_versions").fetchone()[0] == 2


def test_fancard_without_custom_image_saves_metadata_and_stays_incremental(tmp_path: Path):
    archive = service(tmp_path)
    no_image = payload()
    no_image["body"]["supporterCardImageUrl"] = None
    first_status, version = archive.save_fancard(no_image, None, None)
    second_status, same_version = archive.save_fancard(no_image, None, None)

    assert (first_status, second_status) == ("new", "unchanged")
    assert same_version == version
    assert not (version / "card.jpeg").exists()
    markdown = (version / "fancard.md").read_text(encoding="utf-8")
    assert "未提供自訂 Fan Card 卡面" in markdown
    manifest = json.loads((version / "manifest.json").read_text(encoding="utf-8"))
    assert sorted(manifest["files"]) == ["fancard.json", "fancard.md"]
    row = archive.db.latest_fancard_version("alice", "2026-10")
    assert row["image_path"] == ""
    assert row["image_sha256"] == ""
    assert archive.verify() == []


def test_clear_posts_preserves_fancards_and_creator_records(tmp_path: Path):
    archive = service(tmp_path)
    archive.save_fancard(payload(), b"jpeg-data", "image/jpeg")
    post = Post(
        post_id="10", creator_id="alice", creator_name="Alice", title="old",
        published_at=datetime(2026, 10, 1), url="https://www.fanbox.cc/@alice/posts/10",
        blocks=[ContentBlock(type="paragraph", text="old data")],
        content_fingerprint="old-fingerprint",
    )
    archive.save(post, download_assets=False)
    post_path = Path(str(archive.db.post_row("10")["local_path"]))
    card_path = archive.config.storage.output_dir / "alice/fancards/2026-10"

    assert archive.clear_posts() == 1
    assert not post_path.exists()
    assert card_path.is_dir()
    assert archive.db.post_row("10") is None
    assert archive.db.creator_row("alice") is not None
    with archive.db.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM fancard_versions").fetchone()[0] == 1
