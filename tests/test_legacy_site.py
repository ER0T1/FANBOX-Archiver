import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import fanbox_archiver.cli as cli
from fanbox_archiver.archive_lock import ArchiveLock
from fanbox_archiver.cli import app
from fanbox_archiver.legacy_site import cleanup_owned_archive, remove_legacy_static_site
from fanbox_archiver.webapp import create_app
from test_reader import dynamic_archive

runner = CliRunner()
GENERATED_INDEX = (
    '<!doctype html>\n<html lang="zh-Hant"><head><title>FANBOX Archive</title>'
    '<script src="_site/assets/theme.js"></script></head><body></body></html>'
)


def _snapshot(root: Path) -> dict[str, str]:
    """Every archive file outside the old static site, with its content hash."""
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_file() and not relative.startswith(("_site/", "._site")) and relative != "index.html":
            result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _old_site(root: Path) -> None:
    for name in ("_site", "._site.replaced"):
        (root / name / "assets").mkdir(parents=True)
        (root / name / "build.json").write_text("{}", encoding="utf-8")
        (root / name / "assets" / "app.js").write_text("// old", encoding="utf-8")
    (root / f"._site.{'a' * 32}.tmp" / "posts").mkdir(parents=True)
    (root / "index.html").write_text(GENERATED_INDEX, encoding="utf-8")


def _cli_config(tmp_path: Path, config) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        "storage:\n"
        f"  output_dir: {json.dumps(str(config.storage.output_dir))}\n"
        f"  database: {json.dumps(str(config.storage.database))}\n",
        encoding="utf-8",
    )
    return path


def test_generated_static_site_is_removed_and_nothing_else_changes(tmp_path: Path):
    config, _ = dynamic_archive(tmp_path)
    root = config.storage.output_dir
    before = _snapshot(root)
    _old_site(root)
    (root / "notes.html").write_text("<p>mine</p>", encoding="utf-8")

    result = remove_legacy_static_site(root)

    assert sorted(result.removed) == sorted(["_site/", "._site.replaced/", f"._site.{'a' * 32}.tmp/", "index.html"])
    assert result.notices == []
    assert not (root / "_site").exists() and not (root / "index.html").exists()
    assert (root / "notes.html").is_file()
    assert _snapshot(root) == {**before, "notes.html": _snapshot(root)["notes.html"]}
    assert remove_legacy_static_site(root).removed == []  # idempotent


def test_items_that_may_not_be_ours_are_kept_and_reported(tmp_path: Path):
    root = tmp_path / "FANBOX"
    (root / "_site").mkdir(parents=True)
    (root / "_site" / "my-notes.txt").write_text("keep", encoding="utf-8")  # no build.json
    (root / "index.html").write_text("<title>My own page</title>", encoding="utf-8")
    (root / "._site.not-a-build.tmp").mkdir()  # name is not the staging pattern

    result = remove_legacy_static_site(root)

    assert result.removed == []
    assert (root / "_site" / "my-notes.txt").read_text(encoding="utf-8") == "keep"
    assert (root / "index.html").is_file() and (root / "._site.not-a-build.tmp").is_dir()
    assert any("_site" in notice and "build.json" in notice for notice in result.notices)
    assert any("index.html" in notice for notice in result.notices)


def _junction(link: Path, target: Path) -> bool:
    if os.name == "nt":
        done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                              capture_output=True, check=False)
        return done.returncode == 0
    try:
        link.symlink_to(target, target_is_directory=True)
        return True
    except OSError:
        return False


def test_links_and_junctions_are_never_followed_or_removed(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "build.json").write_text("{}", encoding="utf-8")
    (outside / "precious.txt").write_text("outside the archive", encoding="utf-8")
    root = tmp_path / "FANBOX"
    root.mkdir()
    if not _junction(root / "_site", outside):
        pytest.skip("cannot create a junction or symbolic link here")
    result = remove_legacy_static_site(root)
    assert result.removed == []
    assert (outside / "precious.txt").read_text(encoding="utf-8") == "outside the archive"
    assert any("連結" in notice for notice in result.notices)

    # A link inside a generated site stops the whole directory from being deleted.
    (root / "_site").unlink() if os.name != "nt" else os.rmdir(root / "_site")
    (root / "_site").mkdir()
    (root / "_site" / "build.json").write_text("{}", encoding="utf-8")
    assert _junction(root / "_site" / "inner", outside)
    result = remove_legacy_static_site(root)
    assert result.removed == [] and (outside / "precious.txt").is_file()
    assert any("資料夾內含連結" in notice for notice in result.notices)


def test_a_failed_delete_is_reported_and_retried_later(tmp_path: Path, monkeypatch):
    root = tmp_path / "FANBOX"
    root.mkdir()
    _old_site(root)

    def locked(path, *args, **kwargs):
        raise PermissionError("in use")

    monkeypatch.setattr(shutil, "rmtree", locked)
    result = remove_legacy_static_site(root)
    assert "index.html" in result.removed  # the file still goes
    assert (root / "_site").is_dir()
    assert any("下次啟動再試" in notice for notice in result.notices)
    monkeypatch.undo()
    assert "_site/" in remove_legacy_static_site(root).removed


def test_cleanup_waits_while_another_process_owns_the_archive(tmp_path: Path):
    config, _ = dynamic_archive(tmp_path)
    root = config.storage.output_dir
    _old_site(root)
    other = ArchiveLock(root)
    assert other.try_acquire()
    try:
        assert cleanup_owned_archive(config).removed == []
        assert (root / "_site").is_dir()
    finally:
        other.release()
    assert "_site/" in cleanup_owned_archive(config).removed


def test_index_command_explains_the_removal(tmp_path: Path):
    config, _ = dynamic_archive(tmp_path)
    result = runner.invoke(app, ["index", "--force", "--config", str(_cli_config(tmp_path, config))])
    assert result.exit_code == 1
    assert "已移除" in result.output and "serve" in result.output
    assert not (config.storage.output_dir / "_site").exists()
    assert "index" not in runner.invoke(app, ["--help"]).output.split("Commands")[-1].split()


def test_open_opens_folders_and_clear_posts_no_longer_builds_a_site(tmp_path: Path, monkeypatch):
    config, _ = dynamic_archive(tmp_path)
    root = config.storage.output_dir.resolve()
    path = _cli_config(tmp_path, config)
    opened: list[Path] = []
    monkeypatch.setattr(cli, "open_folder", opened.append)

    assert runner.invoke(app, ["open", "--config", str(path)]).exit_code == 0
    assert runner.invoke(app, ["open", "--post", "123", "--version", "1", "--config", str(path)]).exit_code == 0
    assert runner.invoke(app, ["open", "--folder", "--creator", "alice", "--config", str(path)]).exit_code == 0
    assert opened[0] == root
    assert opened[1].name == "v0001" and root in opened[1].parents
    assert opened[2] == root / "alice"

    _old_site(root)
    cleared = runner.invoke(app, ["clear-posts", "--yes", "--config", str(path)])
    assert cleared.exit_code == 0, cleared.output
    assert not (root / "_site").exists() and not (root / "index.html").exists()


@pytest.mark.anyio
async def test_diagnostics_show_items_that_were_not_removed(tmp_path: Path):
    config, _ = dynamic_archive(tmp_path)
    root = config.storage.output_dir
    (root / "index.html").write_text("<title>My own page</title>", encoding="utf-8")
    app_ = create_app(config)
    app_.state.legacy_site = remove_legacy_static_site(root)
    transport = httpx.ASGITransport(app=app_)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        info = (await client.get("/api/diagnostics",
                                 headers={"X-Fanbox-Token": app_.state.session_token})).json()
    assert any("index.html" in notice for notice in info["notices"])
    assert "提示：未刪除舊靜態網站項目「index.html」" in info["text"]


def test_server_start_removes_the_old_site_once_it_owns_the_archive(tmp_path: Path, monkeypatch):
    from fastapi.testclient import TestClient

    import fanbox_archiver.webapp as webapp

    # Never touch the real Windows Task Scheduler from a test.
    monkeypatch.setattr(webapp, "sync_background_schedule", lambda *args, **kwargs: {"state": "unavailable", "message": ""})
    config, _ = dynamic_archive(tmp_path)
    root = config.storage.output_dir
    _old_site(root)
    app_ = create_app(config, run_scheduler=True)
    with TestClient(app_, base_url="http://127.0.0.1"):
        assert not (root / "_site").exists() and not (root / "index.html").exists()
        assert "index.html" in app_.state.legacy_site.removed
    app_.state.jobs.archive_lock.release()
