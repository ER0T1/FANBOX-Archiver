from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from fanbox_archiver.downloader import AssetDownloader, DownloadRateLimitedError, sha256_file
from fanbox_archiver.models import Asset, AssetStatus


def test_stream_download_and_image_validation(tmp_path: Path):
    buffer = BytesIO()
    Image.new("RGB", (8, 6), "red").save(buffer, format="PNG")
    content = buffer.getvalue()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "downloads.fanbox.cc"
        return httpx.Response(200, content=content, headers={
            "content-type": "image/png",
            "content-length": str(len(content)),
            "etag": '"v1"',
        })

    asset = Asset(
        asset_id="a", type="image",
        url="https://downloads.fanbox.cc/images/post/1/a.png",
        original_name="a.png", width=8, height=6,
    )
    target = tmp_path / "a.png"
    progress = []
    with AssetDownloader(
        retries=0, interval=0,
        progress=lambda current, downloaded, total: progress.append((current.asset_id, downloaded, total)),
    ) as downloader:
        downloader.http.close()
        downloader.http = httpx.Client(transport=httpx.MockTransport(handler))
        downloader.download(asset, target)

    assert asset.status == AssetStatus.COMPLETED
    assert asset.size == len(content)
    assert asset.sha256 == sha256_file(target)
    assert progress[-1] == ("a", len(content), len(content))
    assert not (tmp_path / "a.png.part").exists()


def test_rate_limit_stops_without_retrying(tmp_path: Path):
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(429)

    asset = Asset(
        asset_id="f", type="file",
        url="https://downloads.fanbox.cc/files/post/1/f.bin",
    )
    with AssetDownloader(retries=3, interval=0) as downloader:
        downloader.http.close()
        downloader.http = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            downloader.download(asset, tmp_path / "f.bin")
        except DownloadRateLimitedError:
            pass
        else:
            raise AssertionError("expected rate limit error")
    assert requests == 1
