from datetime import datetime
from pathlib import Path

import pytest

from fanbox_archiver.config import AppConfig, StorageConfig
from fanbox_archiver.models import ContentBlock, Post
from fanbox_archiver.reader import ArchiveReader, ReaderNotFound
from fanbox_archiver.service import ArchiveService


def dynamic_archive(tmp_path: Path) -> tuple[AppConfig, ArchiveReader]:
    config = AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "FANBOX",
        database=tmp_path / "FANBOX" / "backup.db",
    ))
    archive = ArchiveService(config)
    first = Post(
        post_id="123", creator_id="alice", creator_name="Alice",
        title="第一版", published_at=datetime(2026, 10, 1),
        updated_at=datetime(2026, 10, 2),
        url="https://www.fanbox.cc/@alice/posts/123",
        tags=["測試"], fee_required=500,
        blocks=[ContentBlock(type="paragraph", text="第一版正文")],
        content_fingerprint="reader-1",
    )
    assert archive.save(first).value == "completed"
    second = first.model_copy(deep=True)
    second.title = "第二版"
    second.updated_at = datetime(2026, 10, 3)
    second.blocks = [ContentBlock(type="paragraph", text="第二版正文")]
    second.content_fingerprint = "reader-2"
    assert archive.save(second).value == "completed"
    archive.save_fancard({"body": {
        "plan": {
            "creatorId": "alice", "title": "Gold", "fee": 1000,
            "description": "Password: private", "perks": [
                {"name": "discord", "available": True, "supporterAccessible": True},
            ],
            "user": {"name": "Alice"},
        },
        "supportStartDatetime": "2026-09-01T00:00:00+09:00",
        "supportTransactions": [
            {"id": "private-transaction", "targetMonth": "2026-10"},
        ],
        "supporterCardImageUrl": "https://example.test/card.jpeg",
    }}, b"jpeg-data", "image/jpeg")
    return config, ArchiveReader(config)


def test_reader_lists_and_loads_versions_without_static_index(tmp_path: Path):
    config, reader = dynamic_archive(tmp_path)

    assert not (config.storage.output_dir / "_site").exists()
    listing = reader.list_posts()
    assert listing["total"] == 1
    assert listing["items"][0]["title"] == "第二版"
    assert listing["items"][0]["version_count"] == 2
    assert listing["items"][0]["fee_required"] == 500
    assert listing["items"][0]["tags"] == ["測試"]
    assert "cover_url" in listing["items"][0]

    latest = reader.post("123")
    assert latest["version"] == 2
    assert latest["blocks"][0]["text"] == "第二版正文"
    assert [item["number"] for item in latest["versions"]] == [1, 2]
    assert reader.post("123", version=1)["title"] == "第一版"


def test_reader_pins_creator_posts_and_builds_contextual_navigation(tmp_path: Path):
    config, reader = dynamic_archive(tmp_path)
    archive = ArchiveService(config)
    pinned = Post(
        post_id="122", creator_id="alice", creator_name="Alice",
        title="較舊的置頂投稿", published_at=datetime(2026, 9, 1),
        updated_at=datetime(2026, 9, 1),
        url="https://www.fanbox.cc/@alice/posts/122",
        blocks=[ContentBlock(type="paragraph", text="置頂內容")],
        raw={"isPinned": True}, content_fingerprint="reader-pinned",
    )
    assert archive.save(pinned, download_assets=False).value == "completed"

    creator_page = reader.list_posts(creator="alice", page=1, page_size=1)
    assert creator_page["total"] == 2
    assert creator_page["pages"] == 2
    assert creator_page["items"][0]["post_id"] == "122"
    assert creator_page["items"][0]["is_pinned"] is True
    assert reader.post("122")["is_pinned"] is True

    creator_navigation = reader.post_navigation("122", creator="alice")
    assert creator_navigation["previous"] is None
    assert creator_navigation["next"]["post_id"] == "123"
    assert creator_navigation["position"] == 1
    assert creator_navigation["total"] == 2

    global_navigation = reader.post_navigation("123")
    assert global_navigation["previous"] is None
    assert global_navigation["next"]["post_id"] == "122"


def test_reader_filters_creator_posts_by_saved_tags_across_pages(tmp_path: Path):
    config, reader = dynamic_archive(tmp_path)
    archive = ArchiveService(config)
    for post_id, title, tags in (
        ("124", "共同標籤投稿", ["測試", "共同"]),
        ("125", "另一篇共同投稿", ["共同", "限定"]),
    ):
        post = Post(
            post_id=post_id, creator_id="alice", creator_name="Alice", title=title,
            published_at=datetime(2026, 10, int(post_id) - 120),
            updated_at=datetime(2026, 10, int(post_id) - 120),
            url=f"https://www.fanbox.cc/@alice/posts/{post_id}", tags=tags,
            blocks=[ContentBlock(type="paragraph", text=title)],
            content_fingerprint=f"reader-tag-{post_id}",
        )
        assert archive.save(post, download_assets=False).value == "completed"

    first_page = reader.list_posts(creator="alice", page=1, page_size=1)
    assert first_page["creator_total"] == 3
    assert first_page["tag_facets"] == [
        {"name": "共同", "count": 2},
        {"name": "測試", "count": 2},
        {"name": "限定", "count": 1},
    ]
    filtered = reader.list_posts(creator="alice", tag="共同", page=99, page_size=1)
    assert filtered["total"] == 2
    assert filtered["pages"] == 2
    assert filtered["page"] == 2
    assert filtered["items"][0]["post_id"] == "124"
    assert reader.list_posts(creator="alice", query="另一篇", tag="共同")["total"] == 1
    navigation = reader.post_navigation("125", creator="alice", tag="共同")
    assert navigation["position"] == 1
    assert navigation["total"] == 2
    assert navigation["next"]["post_id"] == "124"


def test_reader_resolves_fanbox_embed_to_local_only_when_readable(tmp_path: Path):
    config, reader = dynamic_archive(tmp_path)
    archive = ArchiveService(config)
    source = Post(
        post_id="124", creator_id="alice", creator_name="Alice",
        title="含內嵌投稿", published_at=datetime(2026, 10, 4),
        updated_at=datetime(2026, 10, 4),
        url="https://www.fanbox.cc/@alice/posts/124", post_type="article",
        blocks=[ContentBlock(
            type="embed", url="https://www.fanbox.cc/@bob/posts/99",
            raw={"urlEmbedId": "linked"},
        )],
        raw={"body": {"urlEmbedMap": {"linked": {
            "type": "fanbox.post", "postInfo": {
                "id": "99", "creatorId": "bob", "title": "內嵌標題",
                "excerpt": "內嵌摘要", "feeRequired": 300,
                "publishedDatetime": "2026-09-01T12:00:00+09:00",
                "user": {"name": "Bob"},
            },
        }}}},
        content_fingerprint="embed-source",
    )
    archive.save(source, download_assets=False)

    external = reader.post("124")["blocks"][0]["embed"]
    assert external["title"] == "內嵌標題"
    assert external["excerpt"] == "內嵌摘要"
    assert external["fee_required"] == 300
    assert external["fanbox_url"] == "https://www.fanbox.cc/@bob/posts/99"
    assert external["local_available"] is False

    target = Post(
        post_id="99", creator_id="bob", creator_name="Bob", title="本機投稿",
        published_at=datetime(2026, 9, 1), updated_at=datetime(2026, 9, 1),
        url="https://www.fanbox.cc/@bob/posts/99", post_type="text",
        blocks=[ContentBlock(type="paragraph", text="本機內容")],
        content_fingerprint="embed-target",
    )
    archive.save(target, download_assets=False)
    assert reader.post("124")["blocks"][0]["embed"]["local_available"] is True


def test_reader_search_escapes_sql_wildcards(tmp_path: Path):
    _, reader = dynamic_archive(tmp_path)
    assert reader.list_posts(query="第二")["total"] == 1
    assert reader.list_posts(query="%")["total"] == 0


def test_reader_rejects_invalid_or_missing_post(tmp_path: Path):
    _, reader = dynamic_archive(tmp_path)
    with pytest.raises(ReaderNotFound):
        reader.post("../123")
    with pytest.raises(ReaderNotFound):
        reader.post("999")


def test_reader_lists_fancards_without_exposing_transactions(tmp_path: Path):
    _, reader = dynamic_archive(tmp_path)
    cards = reader.list_fancards()
    assert len(cards) == 1
    assert cards[0]["plan_title"] == "Gold"
    assert cards[0]["image_url"].endswith("/versions/1/image")

    card = reader.fancard("alice", "2026-10")
    assert card["description"] == "Password: private"
    assert card["support_months"] == ["2026-10"]
    assert card["perks"] == [{
        "key": "discord", "label": "加入 Discord 伺服器", "status": "accessible",
        "status_label": "目前可使用",
        "description": "連結 Discord 後，即可加入創作者準備的 Discord 伺服器並參與社群交流。",
        "guidance": "Discord 連結可在帳號設定中編輯。",
        "settings_url": "https://www.fanbox.cc/user/settings",
        "settings_label": "帳號設定",
        "action_url": "https://www.fanbox.cc/@alice/plans",
        "action_label": "在 FANBOX 開啟 Discord",
        "available": True, "supporter_accessible": True,
    }]
    assert "private-transaction" not in str(card)
    assert reader.fancard_image("alice", "2026-10", 1).path.read_bytes() == b"jpeg-data"


def test_reader_lists_creators(tmp_path: Path):
    _, reader = dynamic_archive(tmp_path)
    creators = reader.list_creators()
    assert creators[0]["creator_id"] == "alice"
    assert creators[0]["post_count"] == 1

    creator = reader.creator("alice")
    assert creator["fanbox_url"] == "https://www.fanbox.cc/@alice"
    assert creator["fancard_count"] == 1

    with pytest.raises(ReaderNotFound):
        reader.creator("missing")
