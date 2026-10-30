from __future__ import annotations

import argparse
import asyncio
import json
import platform
import shutil
import socket
import statistics
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import httpx
import uvicorn

from fanbox_archiver.config import AppConfig, MarkdownConfig, StorageConfig
from fanbox_archiver.indexer import IndexBuilder
from fanbox_archiver.models import ContentBlock, Post
from fanbox_archiver.reader import ArchiveReader
from fanbox_archiver.service import ArchiveService
from fanbox_archiver.webapp import create_app


def synthetic_posts(creator_count: int, post_count: int) -> list[Post]:
    """Create deterministic, deidentified posts without network resources."""
    if creator_count < 1 or post_count < 1:
        raise ValueError("creator_count and post_count must be positive")
    start = datetime(2025, 1, 1, tzinfo=UTC)
    posts: list[Post] = []
    for index in range(post_count):
        creator_number = index % creator_count
        creator_id = f"synthetic-{creator_number:03d}"
        keyword = " benchmark-keyword" if index == post_count // 2 else ""
        posts.append(Post(
            post_id=str(10_000_000 + index),
            creator_id=creator_id,
            creator_name=f"Synthetic Creator {creator_number:03d}",
            title=f"Synthetic Post {index:04d}{keyword}",
            published_at=start + timedelta(hours=index),
            updated_at=start + timedelta(hours=index, minutes=5),
            url=f"https://www.fanbox.cc/@{creator_id}/posts/{10_000_000 + index}",
            tags=["synthetic", f"group-{index % 8}"],
            blocks=[ContentBlock(
                type="paragraph",
                text=(f"Deidentified benchmark body {index:04d}. " * 8).strip(),
            )],
            content_fingerprint=f"synthetic-fingerprint-{index:08d}",
        ))
    return posts


def _elapsed_ms(action: Callable[[], Any]) -> tuple[Any, float]:
    started = time.perf_counter()
    value = action()
    return value, round((time.perf_counter() - started) * 1000, 3)


def _median_ms(action: Callable[[], Any], repeats: int) -> float:
    samples = [_elapsed_ms(action)[1] for _ in range(repeats)]
    return round(statistics.median(samples), 3)


def _query_plans(config: AppConfig) -> dict[str, list[str]]:
    statements = {
        "list": (
            "SELECT p.post_id,c.name,(SELECT COUNT(*) FROM post_versions v WHERE v.post_id=p.post_id) "
            "FROM posts p "
            "JOIN creators c ON c.creator_id=p.creator_id "
            "ORDER BY p.published_at DESC,p.post_id DESC LIMIT 50",
            (),
        ),
        "creator_list": (
            "SELECT p.post_id,c.name,(SELECT COUNT(*) FROM post_versions v WHERE v.post_id=p.post_id) "
            "FROM posts p "
            "JOIN creators c ON c.creator_id=p.creator_id "
            "WHERE p.creator_id=? "
            "ORDER BY p.is_pinned DESC,p.published_at DESC,p.post_id DESC LIMIT 50",
            ("synthetic-000",),
        ),
        "search": (
            "SELECT p.post_id,c.name,(SELECT COUNT(*) FROM post_versions v WHERE v.post_id=p.post_id) "
            "FROM posts p "
            "JOIN creators c ON c.creator_id=p.creator_id "
            "WHERE p.title LIKE ? OR p.post_id LIKE ? OR p.creator_id LIKE ? OR c.name LIKE ? "
            "ORDER BY p.published_at DESC,p.post_id DESC LIMIT 50",
            ("%benchmark-keyword%",) * 4,
        ),
    }
    plans: dict[str, list[str]] = {}
    reader = ArchiveReader(config)
    with reader.db.connect() as db:
        for name, (sql, values) in statements.items():
            plans[name] = [str(row[3]) for row in db.execute(f"EXPLAIN QUERY PLAN {sql}", values)]
    return plans


def _measure_sqlite(config: AppConfig, repeats: int) -> dict[str, float]:
    list_sql = (
        "SELECT p.*,c.name AS creator_name,"
        "(SELECT COUNT(*) FROM post_versions v WHERE v.post_id=p.post_id) AS version_count,"
        "(SELECT MAX(v.version_number) FROM post_versions v "
        " WHERE v.post_id=p.post_id AND v.status='completed') AS latest_version "
        "FROM posts p JOIN creators c ON c.creator_id=p.creator_id "
        "ORDER BY p.published_at DESC,p.post_id DESC LIMIT 50"
    )
    search_sql = (
        "SELECT p.*,c.name AS creator_name,"
        "(SELECT COUNT(*) FROM post_versions v WHERE v.post_id=p.post_id) AS version_count,"
        "(SELECT MAX(v.version_number) FROM post_versions v "
        " WHERE v.post_id=p.post_id AND v.status='completed') AS latest_version "
        "FROM posts p JOIN creators c ON c.creator_id=p.creator_id "
        "WHERE p.title LIKE ? OR p.post_id LIKE ? OR p.creator_id LIKE ? OR c.name LIKE ? "
        "ORDER BY p.published_at DESC,p.post_id DESC LIMIT 50"
    )
    reader = ArchiveReader(config)

    def execute(sql: str, values: tuple[str, ...] = ()) -> list[Any]:
        with reader.db.connect() as db:
            return list(db.execute(sql, values))

    return {
        "list_median": _median_ms(lambda: execute(list_sql), repeats),
        "search_median": _median_ms(
            lambda: execute(search_sql, ("%benchmark-keyword%",) * 4), repeats
        ),
    }


async def _measure_api(config: AppConfig, repeats: int) -> dict[str, float]:
    app = create_app(config)
    app.state.jobs.close()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async def request(path: str) -> float:
            started = time.perf_counter()
            response = await client.get(path)
            response.raise_for_status()
            return (time.perf_counter() - started) * 1000

        list_samples = [await request("/api/posts?page=1&page_size=50") for _ in range(repeats)]
        search_samples = [await request("/api/posts?q=benchmark-keyword") for _ in range(repeats)]
    return {
        "list_median": round(statistics.median(list_samples), 3),
        "search_median": round(statistics.median(search_samples), 3),
    }


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _measure_frontend(config: AppConfig, browser_name: str, post_count: int) -> float:
    from playwright.sync_api import sync_playwright

    app = create_app(config)
    app.state.jobs.close()
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", access_log=False,
    ))
    thread = threading.Thread(target=server.run, name="benchmark-server", daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base_url}/api/health", timeout=0.5).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("benchmark GUI server did not start")

    try:
        with sync_playwright() as playwright:
            browser = (
                playwright.chromium.launch(headless=True)
                if browser_name == "chromium"
                else playwright.chromium.launch(channel=browser_name, headless=True)
            )
            page = browser.new_page(locale="zh-TW", timezone_id="Asia/Taipei")
            started = time.perf_counter()
            page.goto(base_url, wait_until="networkidle")
            page.get_by_text(f"{post_count} 篇備份", exact=True).wait_for()
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            browser.close()
            return elapsed
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def run_benchmark(
    root: Path,
    *,
    creator_count: int = 20,
    post_count: int = 1000,
    repeats: int = 5,
    browser: str = "none",
) -> dict[str, Any]:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    archive_root = root / "FANBOX"
    config = AppConfig(
        storage=StorageConfig(output_dir=archive_root, database=archive_root / "backup.db"),
        markdown=MarkdownConfig(enabled=False),
    )
    posts = synthetic_posts(creator_count, post_count)
    service = ArchiveService(config)

    _, archive_write_ms = _elapsed_ms(
        lambda: [service.save(post, download_assets=False) for post in posts]
    )
    reader = ArchiveReader(config)
    reader_timings = {
        "list_median": _median_ms(lambda: reader.list_posts(page_size=50), repeats),
        "creator_list_median": _median_ms(
            lambda: reader.list_posts(page_size=50, creator="synthetic-000"), repeats
        ),
        "search_median": _median_ms(
            lambda: reader.list_posts(page_size=50, query="benchmark-keyword"), repeats
        ),
    }

    json_paths = sorted(archive_root.glob("*/**/versions/*/post.json"))
    payloads, disk_read_ms = _elapsed_ms(lambda: [path.read_bytes() for path in json_paths])
    parsed, json_parse_ms = _elapsed_ms(lambda: [json.loads(data) for data in payloads])
    if len(parsed) != post_count:
        raise RuntimeError(f"expected {post_count} JSON posts, found {len(parsed)}")

    builder = IndexBuilder(config)
    first_build, static_first_ms = _elapsed_ms(builder.build)
    reused_build, static_reuse_ms = _elapsed_ms(builder.build)
    api_timings = asyncio.run(_measure_api(config, repeats))
    frontend_ms = None if browser == "none" else _measure_frontend(config, browser, post_count)

    result: dict[str, Any] = {
        "schema": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "browser": browser,
        },
        "dataset": {
            "creators": creator_count,
            "posts": post_count,
            "json_files": len(json_paths),
            "synthetic": True,
            "network_requests": 0,
        },
        "timings_ms": {
            "archive_write": archive_write_ms,
            "disk_read_all_json": disk_read_ms,
            "json_parse_all": json_parse_ms,
            "sqlite": _measure_sqlite(config, repeats),
            "reader": reader_timings,
            "static_index_first": static_first_ms,
            "static_index_reuse": static_reuse_ms,
            "api": api_timings,
            "frontend_first_render": frontend_ms,
        },
        "static_index": {
            "first_rendered": first_build.rendered,
            "first_reused": first_build.reused,
            "reuse_rendered": reused_build.rendered,
            "reuse_reused": reused_build.reused,
            "warnings": len(reused_build.warnings),
        },
        "query_plans": _query_plans(config),
    }
    (root / "benchmark.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def _print_summary(result: dict[str, Any], output: Path) -> None:
    timings = result["timings_ms"]
    print(f"Synthetic dataset: {result['dataset']['creators']} creators / {result['dataset']['posts']} posts")
    print(f"Archive write: {timings['archive_write']:.3f} ms")
    print(f"Disk read / JSON parse: {timings['disk_read_all_json']:.3f} / {timings['json_parse_all']:.3f} ms")
    print(f"SQLite list / search: {timings['sqlite']['list_median']:.3f} / {timings['sqlite']['search_median']:.3f} ms")
    print(f"Reader list / search: {timings['reader']['list_median']:.3f} / {timings['reader']['search_median']:.3f} ms")
    print(f"Static index first / reuse: {timings['static_index_first']:.3f} / {timings['static_index_reuse']:.3f} ms")
    print(f"API list / search: {timings['api']['list_median']:.3f} / {timings['api']['search_median']:.3f} ms")
    print(f"Frontend first render: {timings['frontend_first_render']} ms")
    print(f"JSON result: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deidentified FANBOX archive benchmark")
    parser.add_argument("--root", type=Path, default=Path(".tmp/benchmark-archive"))
    parser.add_argument("--creators", type=int, default=20)
    parser.add_argument("--posts", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--browser", choices=("none", "chromium", "chrome", "msedge"), default="chrome")
    parser.add_argument("--reset", action="store_true", help="delete the selected benchmark root first")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        Path.cwd().resolve().relative_to(root)
    except ValueError:
        pass
    else:
        parser.error("benchmark root must not be the repository directory or one of its parents")
    if root.exists() and any(root.iterdir()):
        if not args.reset:
            parser.error(f"benchmark root is not empty: {root}; pass --reset or choose another root")
        shutil.rmtree(root)
    result = run_benchmark(
        root,
        creator_count=args.creators,
        post_count=args.posts,
        repeats=args.repeats,
        browser=args.browser,
    )
    _print_summary(result, root / "benchmark.json")


if __name__ == "__main__":
    main()
