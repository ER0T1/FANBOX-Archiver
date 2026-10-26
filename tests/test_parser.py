from pathlib import Path

from fanbox_archiver.parser import HtmlPostParser, StructuredPostParser


ROOT = Path(__file__).resolve().parents[1]


def test_example_1_extracts_nine_original_images():
    post = HtmlPostParser().parse_file(ROOT / "範例1.html")
    assert post.post_id == "12805939"
    assert post.creator_id == "henreader"
    assert post.title == "へんりいだオンリーショップ、スタートです！"
    assert len(post.assets) == 9
    assert all("/w/1200/" not in asset.url for asset in post.assets)
    assert all(asset.url.startswith("https://downloads.fanbox.cc/images/post/") for asset in post.assets)
    image_blocks = [block for block in post.blocks if block.type == "image"]
    assert len(image_blocks) == 9
    special_site = [block for block in post.blocks if block.url and "melonbooks.co.jp/tags" in block.url]
    assert len(special_site) == 0  # normal links are represented inside paragraph text
    assert sum("melonbooks.co.jp/tags" in (block.text or "") for block in post.blocks) == 1


def test_structured_article_preserves_order():
    payload = {"body": {
        "id": "42", "creatorId": "alice", "title": "測試", "type": "article",
        "publishedDatetime": "2026-01-02T03:04:05+09:00",
        "body": {
            "blocks": [
                {"type": "p", "text": "前文"},
                {"type": "image", "imageId": "i1"},
                {"type": "p", "text": "後文"},
            ],
            "imageMap": {"i1": {"id": "i1", "originalUrl": "https://downloads.fanbox.cc/images/post/42/a.png"}},
        },
    }}
    post = StructuredPostParser().parse(payload)
    assert [block.type for block in post.blocks] == ["paragraph", "image", "paragraph"]
    assert post.assets[0].url.endswith("a.png")


def test_structured_article_preserves_bold_ranges_and_creator_icon():
    payload = {"body": {
        "id": "43", "creatorId": "alice", "title": "bold", "type": "article",
        "user": {"name": "Alice", "iconUrl": "https://pixiv.pximg.net/icon.jpeg"},
        "body": {"blocks": [{
            "type": "p", "text": "Alpha Bold Omega",
            "styles": [{"type": "bold", "offset": 6, "length": 4}],
        }]},
    }}
    post = StructuredPostParser().parse(payload)
    assert post.creator_icon_url == "https://pixiv.pximg.net/icon.jpeg"
    assert post.blocks[0].styles[0].type == "bold"
    assert post.blocks[0].styles[0].offset == 6
    assert post.blocks[0].styles[0].length == 4


def test_structured_article_resolves_fanbox_embed_and_downloads_cover():
    payload = {"body": {
        "id": "44", "creatorId": "alice", "title": "embed", "type": "article",
        "body": {
            "blocks": [{"type": "url_embed", "urlEmbedId": "linked"}],
            "urlEmbedMap": {"linked": {
                "type": "fanbox.post",
                "postInfo": {
                    "id": "99", "creatorId": "bob", "title": "連結文章",
                    "excerpt": "卡片摘要", "feeRequired": 300,
                    "cover": {"url": "https://downloads.fanbox.cc/images/post/99/cover.jpeg"},
                },
            }},
        },
    }}
    post = StructuredPostParser().parse(payload)
    block = post.blocks[0]
    assert block.type == "embed"
    assert block.url == "https://www.fanbox.cc/@bob/posts/99"
    assert block.name == "連結文章"
    assert block.text == "卡片摘要"
    assert block.asset_id == "url-embed-linked"
    assert post.assets[0].url.endswith("cover.jpeg")


def test_structured_parser_accepts_nested_post_response():
    payload = {"body": {"post": {
        "id": "7", "creatorId": "alice", "title": "nested", "type": "text",
        "body": {"text": "hello"},
    }}}
    post = StructuredPostParser().parse(payload)
    assert post.post_id == "7"
    assert post.blocks[0].text == "hello"


def test_structured_file_name_keeps_extension():
    payload = {"body": {"post": {
        "id": "8", "creatorId": "alice", "title": "files", "type": "file",
        "body": {"files": [{
            "id": "f1", "name": "jp", "extension": "zip",
            "url": "https://downloads.fanbox.cc/files/post/8/random.zip",
        }]},
    }}}
    post = StructuredPostParser().parse(payload)
    assert post.assets[0].original_name == "jp.zip"


def test_example_2_extracts_attachments():
    post = HtmlPostParser().parse_file(ROOT / "範例2.html")
    assert post.post_id == "12800930"
    assert post.creator_id == "sikosiya"
    assert len(post.assets) == 2
    assert [asset.type for asset in post.assets] == ["file", "file"]
    assert [asset.original_name for asset in post.assets] == ["jp.zip", "en.zip"]
    assert len([block for block in post.blocks if block.type == "file"]) == 2

