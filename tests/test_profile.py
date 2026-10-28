from pathlib import Path

import httpx
import pytest

from fanbox_archiver.client import FanboxClient
from fanbox_archiver.config import AppConfig, StorageConfig
from fanbox_archiver.downloader import sha256_file
from fanbox_archiver.models import AssetStatus, CreatorProfile, CreatorProfileItem
from fanbox_archiver.profile_parser import CreatorProfileParser
from fanbox_archiver.reader import ArchiveReader, ReaderNotFound
from fanbox_archiver.service import ArchiveService
from fanbox_archiver.webapp import create_app


@pytest.fixture
def anyio_backend():
    return "asyncio"


def profile(description: str = "第一行\n第二行") -> CreatorProfile:
    item = CreatorProfileItem(
        type="website", label="Site", url="https://example.test", description="作品集"
    )
    value = CreatorProfile(
        creator_id="alice", name="Alice", description=description,
        profile_items=[item], has_adult_content=True, is_accepting_request=True,
        fanbox_url="https://www.fanbox.cc/@alice", raw={"private": "archive-only"},
    )
    value.content_fingerprint = value.calculate_fingerprint()
    return value


def config(tmp_path: Path) -> AppConfig:
    return AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "FANBOX", database=tmp_path / "FANBOX" / "backup.db"
    ))


def test_profile_parser_normalizes_and_fingerprint_is_stable():
    payload = {"body": {
        "creatorId": "alice", "description": "第一行\r\n第二行",
        "hasAdultContent": True, "isAcceptingRequest": True,
        "user": {"name": "Alice", "iconUrl": "https://pixiv.pximg.net/icon.png"},
        "profileItems": [
            {"type": "website", "label": "Site", "url": "https://example.test"},
            {"type": "future", "value": {"text": "unknown but safe"}},
        ],
    }}
    parsed = CreatorProfileParser().parse(payload, "alice")
    assert parsed.description == "第一行\n第二行"
    assert parsed.profile_items[1].type == "future"
    assert parsed.profile_items[1].description == "unknown but safe"
    assert parsed.content_fingerprint == parsed.calculate_fingerprint()

    reordered = {"body": dict(reversed(list(payload["body"].items())))}
    assert CreatorProfileParser().parse(reordered, "alice").content_fingerprint == parsed.content_fingerprint


def test_client_creator_profile_uses_official_endpoint(monkeypatch):
    client = FanboxClient(cookie="test")
    calls = []
    monkeypatch.setattr(client, "_get", lambda path, params=None: (
        calls.append((path, params)) or {"body": {"creatorId": "alice", "user": {"name": "Alice"}}}
    ))
    try:
        result = client.creator_profile("alice")
    finally:
        client.close()
    assert result.name == "Alice"
    assert calls == [("creator.get", {"creatorId": "alice"})]


def test_profile_new_unchanged_updated_and_reader_hides_raw(tmp_path: Path):
    archive = ArchiveService(config(tmp_path))
    first = profile()
    status, first_path = archive.save_profile(first)
    assert status == "new"
    assert first_path.name == "v0001"
    assert (first_path / "profile.json").is_file()
    assert (first_path.parent.parent / "profile.json").is_file()

    status, same_path = archive.save_profile(first)
    assert status == "unchanged"
    assert same_path == first_path
    assert len(archive.db.profile_versions("alice")) == 1

    second = profile("已更新")
    status, second_path = archive.save_profile(second)
    assert status == "updated"
    assert second_path.name == "v0002"

    reader = ArchiveReader(config(tmp_path))
    result = reader.creator_profile("alice")
    assert result["description"] == "已更新"
    assert result["version"] == 2
    assert [item["number"] for item in result["versions"]] == [1, 2]
    assert "raw" not in result and "private" not in str(result)
    assert reader.creator("alice")["profile_version_count"] == 2
    with pytest.raises(ReaderNotFound):
        reader.creator_profile("alice", version=99)

    assert archive.clear_posts() == 0
    assert archive.db.latest_profile_version("alice") is not None
    assert second_path.is_dir()


def test_profile_item_images_are_archived_and_served_locally(monkeypatch, tmp_path: Path):
    import fanbox_archiver.service as service_module

    class FakeDownloader:
        calls = 0

        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def download(self, asset, target):
            self.__class__.calls += 1
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"profile-image")
            asset.status = AssetStatus.COMPLETED
            asset.size = target.stat().st_size
            asset.sha256 = sha256_file(target)
            return asset

    monkeypatch.setattr(service_module, "AssetDownloader", FakeDownloader)
    item = CreatorProfileItem(
        item_id="image-1", type="image",
        image_url="https://pixiv.pximg.net/fanbox/public/images/profile/image-1.jpeg",
    )
    value = CreatorProfile(
        creator_id="alice", name="Alice", profile_items=[item],
        fanbox_url="https://www.fanbox.cc/@alice",
    )
    value.content_fingerprint = value.calculate_fingerprint()
    archive = ArchiveService(config(tmp_path))

    status, path = archive.save_profile(value)

    assert status == "new"
    assert FakeDownloader.calls == 1
    assert (path / "images" / "001_image-1.jpeg").read_bytes() == b"profile-image"
    assert archive.save_profile(value)[0] == "unchanged"
    assert FakeDownloader.calls == 1

    reader = ArchiveReader(config(tmp_path))
    dto = reader.creator_profile("alice")
    assert dto["profile_items"][0]["image_url"].endswith("/items/0/image")
    assert "pixiv.pximg.net" not in str(dto)
    assert reader.creator_profile_item_image("alice", 1, 0).path.read_bytes() == b"profile-image"


@pytest.mark.anyio
async def test_profile_api_and_empty_state(tmp_path: Path):
    archive = ArchiveService(config(tmp_path))
    archive.save_profile(profile())
    app = create_app(config(tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/creators/alice/profile")
        assert response.status_code == 200
        assert response.json()["version"] == 1
        assert "raw" not in response.json()
        versions = await client.get("/api/creators/alice/profile/versions")
        assert versions.json()["items"][0]["number"] == 1
        missing = await client.get("/api/creators/alice/profile?version=99")
        assert missing.status_code == 404
