import json
from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from fanbox_archiver.cli import app
from fanbox_archiver.config import AppConfig, StorageConfig
from fanbox_archiver.indexer import IndexBuilder
from fanbox_archiver.models import ContentBlock, Post, TextStyle
from fanbox_archiver.service import ArchiveService


def archive_fixture(tmp_path: Path) -> tuple[AppConfig, ArchiveService]:
    config = AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "FANBOX",
        database=tmp_path / "FANBOX" / "backup.db",
    ))
    archive = ArchiveService(config)
    archive.db.record_supporting_creators([("alice", "Alice <作者>")])
    first = Post(
        post_id="123", creator_id="alice", creator_name="Alice <作者>",
        title="第一篇 <script>alert(1)</script>",
        published_at=datetime(2026, 10, 1), updated_at=datetime(2026, 10, 2),
        url="https://www.fanbox.cc/@alice/posts/123", tags=["測試", "CJK"],
        fee_required=500, blocks=[
            ContentBlock(
                type="paragraph", text="安全正文 <b>不是 HTML</b> 粗體",
                styles=[TextStyle(type="bold", offset=20, length=2)],
            ),
            ContentBlock(
                type="embed", url="legacy-id",
                raw={"type": "url_embed", "urlEmbedId": "legacy-id"},
            ),
        ],
        raw={
            "secret": "不應進入索引",
            "body": {"urlEmbedMap": {"legacy-id": {
                "type": "fanbox.post",
                "postInfo": {
                    "id": "99", "creatorId": "alice", "title": "舊連結卡片",
                    "excerpt": "既有備份摘要", "feeRequired": 300,
                    "user": {"name": "Alice"},
                },
            }}},
        },
        content_fingerprint="fingerprint-1",
    )
    archive.save(first, download_assets=False)
    second = first.model_copy(deep=True)
    second.title = "更新後標題"
    second.updated_at = datetime(2026, 10, 3)
    second.content_fingerprint = "fingerprint-2"
    archive.save(second, download_assets=False)
    archive.save_fancard({"body": {
        "plan": {"id": "plan", "title": "Gold", "fee": 1000,
                 "description": "Password: private-value", "creatorId": "alice",
                 "user": {"userId": "u1", "name": "Alice"}, "paymentMethod": "card"},
        "supportStartDatetime": "2026-10-01T00:00:00+09:00",
        "supportTransactions": [{"id": "private-tx", "targetMonth": "2026-10",
                                   "paidAmount": 1000, "supporter": {"userId": "private-user"}}],
        "supporterCardImageUrl": "https://example.test/card.jpeg",
    }}, b"jpeg-data", "image/jpeg")
    return config, archive


def test_index_builds_safe_offline_pages_and_omits_private_index_data(tmp_path: Path):
    config, _ = archive_fixture(tmp_path)
    builder = IndexBuilder(config)
    result = builder.build()

    root = config.storage.output_dir
    assert result.rendered == 3
    assert result.reused == 0
    assert (root / "index.html").is_file()
    assert (root / "_site/assets/app.js").is_file()
    assert (root / "_site/assets/theme.js").is_file()
    post_page = (root / "_site/posts/123/v0001.html").read_text(encoding="utf-8")
    assert "安全正文 &lt;b&gt;不是 HTML&lt;/b&gt;" in post_page
    assert "<strong>粗體</strong>" in post_page
    assert "2026年10月01日 08:00" in post_page
    assert "UTC+8" not in post_page
    assert "¥500" in post_page
    assert 'src="../../assets/theme.js"' in post_page
    assert "data-theme-toggle" in post_page
    assert "script-src 'none'" not in post_page
    assert 'class="embed-card"' in post_page
    assert 'href="https://www.fanbox.cc/@alice/posts/99"' in post_page
    assert "舊連結卡片" in post_page
    assert "既有備份摘要" in post_page
    assert "¥300" in post_page
    assert "<script>alert(1)</script>" not in post_page
    card_page = (root / "_site/fancards/alice/2026-10/latest.html").read_text(encoding="utf-8")
    assert "Password: private-value" in card_page
    assert "2026年09月30日 23:00" in card_page
    assert "+09:00" not in card_page
    assert "UTC+8" not in card_page
    assert 'src="../../../assets/theme.js"' in card_page
    assert "data-theme-toggle" in card_page
    assert "方案資訊" in card_page
    assert "方案說明／密碼" not in card_page

    data = (root / "_site/data.js").read_text(encoding="utf-8")
    assert "private-value" not in data
    assert "private-tx" not in data
    assert "private-user" not in data
    assert "不應進入索引" not in data
    assert builder.check() == []


def test_fancard_page_distinguishes_no_card_from_missing_image(tmp_path: Path):
    config, _ = archive_fixture(tmp_path)
    builder = IndexBuilder(config)
    row = {"version_number": 1, "creator_id": "alice", "target_month": "2026-10"}
    body = {
        "plan": {"title": "Gold", "fee": 1000, "user": {"name": "Alice"}},
        "supporterCardImageUrl": None,
    }
    page = builder._fancard_html(body, row, tmp_path / "page.html", tmp_path / "no-card.jpeg", [row])
    assert "本月未提供 Fan Card 卡面。" in page
    assert "卡面圖片遺失。" not in page
    assert "方案資訊" in page


def test_fanbox_embed_links_to_local_backup_only_when_readable(tmp_path: Path):
    config, archive = archive_fixture(tmp_path)
    builder = IndexBuilder(config)
    builder.build()
    page_path = config.storage.output_dir / "_site/posts/123/v0001.html"
    external_page = page_path.read_text(encoding="utf-8")
    assert 'href="https://www.fanbox.cc/@alice/posts/99"' in external_page
    assert "FANBOX Post · 本機備份" not in external_page

    linked = Post(
        post_id="99", creator_id="alice", creator_name="Alice", title="已備份文章",
        published_at=datetime(2026, 9, 1), updated_at=datetime(2026, 9, 1),
        url="https://www.fanbox.cc/@alice/posts/99", post_type="text",
        blocks=[ContentBlock(type="paragraph", text="本機內容")],
        raw={}, content_fingerprint="linked-fingerprint",
    )
    archive.save(linked, download_assets=False)
    builder.build(force=True)
    local_page = page_path.read_text(encoding="utf-8")
    assert 'href="../99/latest.html"' in local_page
    assert "FANBOX Post · 本機備份" in local_page
    assert (config.storage.output_dir / "_site/posts/99/latest.html").is_file()


def test_index_reuses_pages_and_check_reports_missing_page(tmp_path: Path):
    config, _ = archive_fixture(tmp_path)
    builder = IndexBuilder(config)
    builder.build()
    second = builder.build()
    assert second.rendered == 0
    assert second.reused == 3
    rebuilt_data = (config.storage.output_dir / "_site/data.js").read_text(encoding="utf-8")
    assert "測試" in rebuilt_data
    assert '"fee_required":500' in rebuilt_data

    missing = config.storage.output_dir / "_site/posts/123/v0001.html"
    missing.unlink()
    assert any("v0001.html" in issue for issue in builder.check())


def test_index_cli_build_and_check(tmp_path: Path):
    config, _ = archive_fixture(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "storage:\n"
        f"  output_dir: {json.dumps(str(config.storage.output_dir))}\n"
        f"  database: {json.dumps(str(config.storage.database))}\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    built = runner.invoke(app, ["index", "--config", str(config_path)])
    assert built.exit_code == 0, built.output
    assert "索引已建立" in built.output
    checked = runner.invoke(app, ["index", "--check", "--config", str(config_path)])
    assert checked.exit_code == 0, checked.output
    assert "索引驗證通過" in checked.output


def test_open_cli_only_opens_browser_or_folder_when_explicit(tmp_path: Path, monkeypatch):
    config, archive = archive_fixture(tmp_path)
    IndexBuilder(config).build()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "storage:\n"
        f"  output_dir: {json.dumps(str(config.storage.output_dir))}\n"
        f"  database: {json.dumps(str(config.storage.database))}\n",
        encoding="utf-8",
    )
    opened_urls: list[str] = []
    opened_folders: list[Path] = []
    monkeypatch.setattr("fanbox_archiver.cli.webbrowser.open", lambda value: opened_urls.append(value))
    monkeypatch.setattr("fanbox_archiver.cli.os.startfile", lambda value: opened_folders.append(Path(value)))
    runner = CliRunner()

    page = runner.invoke(app, ["open", "--post", "123", "--config", str(config_path)])
    assert page.exit_code == 0, page.output
    assert opened_urls and opened_urls[0].endswith("/_site/posts/123/latest.html")

    folder = runner.invoke(app, ["open", "--folder", "--post", "123", "--version", "1", "--config", str(config_path)])
    assert folder.exit_code == 0, folder.output
    assert opened_folders == [Path(str(archive.db.version_rows("123")[0]["local_path"]))]
