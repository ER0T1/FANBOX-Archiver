import json
from pathlib import Path

import pytest

from fanbox_archiver.client import FanboxClient
from fanbox_archiver.config import AppConfig, StorageConfig
from fanbox_archiver.parser import StructuredPostParser
from fanbox_archiver.profile_parser import CreatorProfileParser
from fanbox_archiver.service import ArchiveService


FIXTURES = Path(__file__).parent / "fixtures" / "fanbox"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("name", "post_type", "block_types", "asset_types"),
    [
        ("article.json", "article", ["paragraph", "image", "file", "embed"], ["image", "file"]),
        ("image.json", "image", ["paragraph", "image"], ["image"]),
        ("file.json", "file", ["paragraph", "file"], ["file"]),
        ("text.json", "text", ["paragraph"], []),
    ],
)
def test_synthetic_post_contract_fixtures(
    name: str, post_type: str, block_types: list[str], asset_types: list[str],
):
    post = StructuredPostParser().parse(load_fixture(name))

    assert post.post_type == post_type
    assert [block.type for block in post.blocks] == block_types
    assert [asset.type for asset in post.assets] == asset_types
    assert post.parse_warnings == []
    assert post.creator_id == "fixture-creator"


def test_article_embed_and_media_keep_contract_details():
    post = StructuredPostParser().parse(load_fixture("article.json"))

    assert post.blocks[0].styles[0].type == "bold"
    assert post.blocks[1].url.endswith("/original.png")
    assert post.blocks[2].name == "fixture.zip"
    assert post.blocks[3].url == "https://www.fanbox.cc/@linked-creator/posts/linked-post"
    assert post.blocks[3].name == "合成連結投稿"


def test_missing_media_warns_and_never_promotes_preview_to_original():
    post = StructuredPostParser().parse(load_fixture("missing-media.json"))

    assert post.assets == []
    assert [block.type for block in post.blocks] == ["raw", "raw", "embed"]
    assert len(post.parse_warnings) == 3
    assert any("不會推測為原始檔" in message for message in post.parse_warnings)
    assert any("missing-file" in message for message in post.parse_warnings)
    assert any("missing-embed" in message for message in post.parse_warnings)
    assert "preview.png" not in json.dumps(
        [asset.model_dump(mode="json") for asset in post.assets], ensure_ascii=False
    )


def test_client_forwards_parser_warnings_to_shared_backup_callback():
    client = FanboxClient(cookie="fixture", request_interval=0)
    messages: list[tuple[str, str]] = []
    client.post_payload_fetcher = lambda _post_id: load_fixture("missing-media.json")
    client.parse_warning_callback = lambda post_id, message: messages.append((post_id, message))
    try:
        post = client.post("1")
    finally:
        client.close()

    assert messages == [(post.post_id, message) for message in post.parse_warnings]


def test_creator_profile_contract_fixture():
    profile = CreatorProfileParser().parse(load_fixture("profile.json"), "fixture-creator")

    assert profile.name == "Fixture Creator"
    assert [item.type for item in profile.profile_items] == ["website", "image"]
    assert profile.profile_items[1].image_url.endswith("fixture-image.png")
    assert profile.parse_warnings == []


def test_creator_profile_missing_optional_fields_produces_warning():
    profile = CreatorProfileParser().parse(
        {"body": {"creatorId": "fixture-creator", "profileItems": "invalid"}},
        "fixture-creator",
    )

    assert profile.name == "fixture-creator"
    assert profile.profile_items == []
    assert len(profile.parse_warnings) == 2
    assert any("創作者名稱" in message for message in profile.parse_warnings)
    assert any("profileItems" in message for message in profile.parse_warnings)


def test_fancard_contract_fixture_saves_without_private_transaction_fields(tmp_path: Path):
    config = AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "archive", database=tmp_path / "archive" / "backup.db"
    ))
    archive = ArchiveService(config)
    archive.db.record_supporting_creators([("fixture-creator", "Fixture Creator")])

    status, version = archive.save_fancard(load_fixture("fancard.json"), None, None)

    assert status == "new"
    markdown = (version / "fancard.md").read_text(encoding="utf-8")
    assert "合成的方案說明" in markdown
    assert "## 方案權益" in markdown
    assert "加入 Discord 伺服器" in markdown
    assert "Discord 連結可在[帳號設定]" in markdown
    assert "https://www.fanbox.cc/user/settings" in markdown
    assert "https://www.fanbox.cc/@fixture-creator/plans" in markdown
    assert "supporterAccessible" not in markdown
    saved = json.loads((version / "fancard.json").read_text(encoding="utf-8"))
    transaction = saved["body"]["supportTransactions"][0]
    assert set(transaction) == {"paidAmount", "targetMonth"}


def test_fixture_directory_contains_no_authentication_material():
    fixture_text = "\n".join(
        path.read_text(encoding="utf-8") for path in FIXTURES.glob("*.json")
    ).casefold()

    assert "cookie" not in fixture_text
    assert "csrf" not in fixture_text
    assert "access_token" not in fixture_text
    assert "refresh_token" not in fixture_text
