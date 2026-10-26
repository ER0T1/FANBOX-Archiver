from datetime import datetime
from pathlib import Path

from fanbox_archiver.markdown import render_markdown
from fanbox_archiver.models import Asset, ContentBlock, Post, TextStyle
from fanbox_archiver.storage import BackupStorage
import fanbox_archiver.storage as storage_module


def test_storage_and_markdown_use_relative_paths(tmp_path: Path):
    post = Post(
        post_id="1", creator_id="creator", creator_name="作者", title="標題",
        published_at=datetime(2026, 1, 2), url="https://www.fanbox.cc/@creator/posts/1",
        assets=[Asset(asset_id="a", type="image", url="https://downloads.fanbox.cc/images/post/1/a.png", original_name="a.png")],
        blocks=[ContentBlock(type="paragraph", text="內文"), ContentBlock(type="image", asset_id="a")],
    )
    storage = BackupStorage(tmp_path)
    storage.assign_asset_paths(post)
    assert post.assets[0].local_path == "images/001.png"
    output = render_markdown(post)
    assert "內文" in output
    assert "![圖片](images/001.png)" in output
    assert storage.post_dir(post) == tmp_path / "creator" / "2026-01-02_1"


def test_publish_version_retries_temporary_windows_lock(tmp_path: Path, monkeypatch):
    temp = tmp_path / ".v0001.tmp"
    final = tmp_path / "v0001"
    temp.mkdir()
    (temp / "post.json").write_text("{}", encoding="utf-8")
    real_replace = storage_module.os.replace
    attempts = 0

    def flaky_replace(source, target):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("temporarily locked")
        return real_replace(source, target)

    monkeypatch.setattr(storage_module.os, "replace", flaky_replace)
    monkeypatch.setattr(storage_module.time, "sleep", lambda seconds: None)
    BackupStorage.publish_version(temp, final)
    assert attempts == 3
    assert (final / "post.json").exists()


def test_markdown_preserves_bold_text_ranges():
    post = Post(
        post_id="2", creator_id="creator", title="bold", url="https://www.fanbox.cc/@creator/posts/2",
        blocks=[ContentBlock(
            type="paragraph", text="Alpha Bold Omega",
            styles=[TextStyle(type="bold", offset=6, length=4)],
        )],
    )
    assert "Alpha **Bold** Omega" in render_markdown(post)
