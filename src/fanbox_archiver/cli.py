from __future__ import annotations

import os
import json
import subprocess
import sys
import webbrowser
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.filesize import decimal
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .client import (
    AccessRestrictedError,
    AuthenticationError,
    FanboxClient,
    RateLimitedError,
    RemoteUnavailableError,
)
from .browser_session import interactive_login, profile_is_authenticated
from .config import AppConfig
from .credentials import cookie_header
from .models import Post
from .parser import HtmlPostParser
from .service import ArchiveService
from .application import BackupEvent, BackupRequest, BackupUseCase
from .logging_setup import configure_logging, get_logger
from .indexer import IndexBuilder
from .security import confined_path, safe_filename


if os.name == "nt":
    # Python may inherit cp950 on Traditional-Chinese Windows even though FANBOX
    # titles commonly contain Japanese characters.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(
    name="fanbox-archiver",
    help="保守、低頻率的 pixivFANBOX 個人本機備份工具。",
    no_args_is_help=True,
)
auth_app = typer.Typer(
    help="建立或驗證安全的 FANBOX 瀏覽器工作階段。",
    invoke_without_command=True,
)
app.add_typer(auth_app, name="auth")
console = Console()


def format_local_time(value: object, timezone: tzinfo | None = None) -> str:
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(timezone).isoformat(timespec="seconds")
    except ValueError:
        return str(value)


def load_config(path: Path) -> AppConfig:
    try:
        settings = AppConfig.load(path)
        configure_logging(settings)
        return settings
    except (OSError, ValidationError) as exc:
        console.print(f"[red]設定檔錯誤：[/red]{exc}")
        raise typer.Exit(2) from exc


def handle_remote_error(exc: Exception) -> None:
    get_logger().error("%s: %s", type(exc).__name__, exc)
    console.print(f"[red]{exc}[/red]")
    raise typer.Exit(1) from exc


def get_cookie(settings: AppConfig, browser: str | None = None) -> str:
    return cookie_header(
        browser,
        profile_dir=None if browser else settings.auth.profile_dir,
        browser_channel=settings.auth.browser_channel,
    )


def verify_login(settings: AppConfig, browser: str | None = None) -> None:
    if browser is None and settings.auth.profile_dir.exists():
        if profile_is_authenticated(settings.auth.profile_dir, channel=settings.auth.browser_channel):
            console.print("[green]登入狀態有效。[/green]")
            return
        console.print("[red]專用瀏覽器登入狀態無效，請重新執行 `fanbox-archiver auth login`。[/red]")
        raise typer.Exit(1)
    cookie = get_cookie(settings, browser)
    if not cookie:
        console.print("[yellow]找不到登入工作階段，請先執行 `fanbox-archiver auth login`。[/yellow]")
        raise typer.Exit(1)
    with FanboxClient(
        cookie=cookie, timeout=settings.download.timeout_seconds,
        request_interval=settings.download.request_interval_seconds,
    ) as client:
        ok = client.verify_auth()
    console.print("[green]登入狀態有效。[/green]" if ok else "[red]登入狀態無效。[/red]")


@auth_app.callback()
def auth(
    ctx: typer.Context,
    browser: Annotated[str | None, typer.Option("--browser", help="從指定瀏覽器讀取 FANBOX Cookie，例如 chrome")] = None,
    config: Annotated[Path, typer.Option("--config", "-c", help="設定檔路徑")] = Path("config.yaml"),
) -> None:
    """未指定子指令時，驗證目前的登入狀態。"""
    if ctx.invoked_subcommand is not None:
        return
    settings = load_config(config)
    try:
        verify_login(settings, browser)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_remote_error(exc)


@auth_app.command("check")
def auth_check(
    browser: Annotated[str | None, typer.Option("--browser", help="從指定瀏覽器讀取 FANBOX Cookie，例如 chrome")] = None,
    config: Annotated[Path, typer.Option("--config", "-c", help="設定檔路徑")] = Path("config.yaml"),
) -> None:
    """驗證專用瀏覽器設定檔或明確指定瀏覽器的登入狀態。"""
    settings = load_config(config)
    try:
        verify_login(settings, browser)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_remote_error(exc)


@auth_app.command("login")
def auth_login(
    timeout_minutes: Annotated[int, typer.Option("--timeout-minutes", min=1, max=30, help="等待手動登入的分鐘數")] = 10,
    config: Annotated[Path, typer.Option("--config", "-c", help="設定檔路徑")] = Path("config.yaml"),
) -> None:
    """開啟專用 Chrome 視窗，由使用者親自登入並保存工作階段。"""
    settings = load_config(config)
    console.print("[cyan]請在即將開啟的專用 Chrome 視窗中正常登入 FANBOX。[/cyan]")
    console.print("程式不會讀取帳號、密碼、2FA 或 CAPTCHA，只等待登入狀態生效。")
    try:
        interactive_login(
            settings.auth.profile_dir,
            channel=settings.auth.browser_channel,
            timeout_seconds=timeout_minutes * 60,
        )
        verify_login(settings)
    except Exception as exc:
        handle_remote_error(exc)


@app.command()
def creators(
    refresh: Annotated[bool, typer.Option("--refresh", help="重新向 FANBOX 取得目前支援中清單")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 輸出，供其他工具使用")] = False,
    browser: Annotated[str | None, typer.Option("--browser", help="從指定瀏覽器讀取 FANBOX Cookie，例如 chrome")] = None,
    config: Annotated[Path, typer.Option("--config", "-c", help="設定檔路徑")] = Path("config.yaml"),
) -> None:
    """列出目前帳號正在支援且可由 API 回傳的繪師。"""
    settings = load_config(config)
    archive = ArchiveService(settings)
    try:
        cached = archive.db.creator_listing()
        if refresh or not cached:
            cookie = get_cookie(settings, browser)
            with FanboxClient(
                cookie=cookie, timeout=settings.download.timeout_seconds,
                request_interval=settings.download.request_interval_seconds,
            ) as client:
                items = client.supporting_creators()
            archive.db.record_supporting_creators([(item.creator_id, item.name) for item in items])
        rows = archive.db.creator_listing()
    except Exception as exc:
        handle_remote_error(exc)
        return
    if json_output:
        console.print_json(json.dumps(rows, ensure_ascii=False))
        return
    table = Table("Creator ID", "名稱", "本機文章", "最後同步", "狀態", "網址")
    for row in rows:
        table.add_row(
            str(row["creator_id"]), str(row["name"]), str(row["post_count"]),
            format_local_time(row["last_sync"]), str(row["status"]), str(row["url"]),
        )
    console.print(table)


@app.command("import-html")
def import_html(
    html: Annotated[Path, typer.Argument(help="已登入瀏覽器另存的完整 HTML")],
    source_url: Annotated[str | None, typer.Option("--url", help="原始投稿 URL（HTML 無法判斷時使用）")] = None,
    download_assets: Annotated[bool, typer.Option("--download-assets/--metadata-only", help="是否下載解析出的原始資源")] = False,
    force: Annotated[bool, typer.Option("--force", help="忽略增量判斷並重新處理")] = False,
    config: Annotated[Path, typer.Option("--config", "-c", help="設定檔路徑")] = Path("config.yaml"),
) -> None:
    """離線解析渲染後的 FANBOX HTML，輸出 post.md 與 post.json。"""
    settings = load_config(config)
    try:
        post = HtmlPostParser().parse_file(html, source_url)
        status = save_with_progress(
            ArchiveService(settings), post, download_assets=download_assets, force=force
        )
    except Exception as exc:
        console.print(f"[red]匯入失敗：[/red]{exc}")
        raise typer.Exit(1) from exc
    console.print(f"[green]已匯入[/green] {post.post_id}：{post.title}（{status.value}）")


def _print_plan(data: dict) -> None:
    table = Table("Creator ID", "Profile", "發現", "新增/更新/重試", "略過")
    for scan in data["scans"]:
        table.add_row(
            scan["creator_id"], str(scan.get("profile") or "-"), str(scan["discovered"]),
            f"{scan['new']}/{scan['updated']}/{scan['retry']}",
            str(scan["skipped"]),
        )
    console.print(table)
    console.print(
        f"合計：新增 {data['new']}、更新 {data['updated']}、重試 {data['retried']}、"
        f"略過 {data['skipped']}、本次上限延後 {data['deferred']}"
    )


class RichBackupEventSink:
    def __init__(self, progress: Progress, task_id) -> None:
        self.progress = progress
        self.task_id = task_id

    def emit(self, event: BackupEvent) -> None:
        data = event.data
        if event.kind == "plan_ready":
            _print_plan(data)
        elif event.kind == "profile_started":
            self.progress.update(
                self.task_id,
                description=f"正在備份 @{data['creator_id']} 的個人資料",
            )
        elif event.kind == "profile_finished":
            preview = "（預覽）" if data.get("dry_run") else ""
            self.progress.console.print(
                f"[cyan]Profile[/cyan] {data['creator_id']}: {data['status']} "
                f"v{int(data.get('version') or 0):04d}{preview}"
            )
        elif event.kind == "profile_warning":
            self.progress.console.print(
                f"[yellow]Profile {data['creator_id']}: {data['message']}[/yellow]"
            )
        elif event.kind == "asset_progress":
            total = data.get("total")
            downloaded = int(data.get("downloaded") or 0)
            amount = f"{decimal(downloaded)}/{decimal(total)}" if total else decimal(downloaded)
            self.progress.update(self.task_id, description=f"{data['name']} {amount}")
        elif event.kind == "item_finished":
            self.progress.update(
                self.task_id, advance=1,
                description=f"{data['creator_id']} / {data['post_id']}",
            )
            if data.get("error"):
                self.progress.console.print(f"[red]{data['post_id']}: {data['error']}[/red]")
            elif data.get("unchanged"):
                self.progress.console.print(f"{data['post_id']}: unchanged")
            else:
                self.progress.console.print(f"{data['post_id']}: {data['status']}")
        elif event.kind == "fancard_finished":
            self.progress.console.print(
                f"[cyan]Fan Card[/cyan] {data['creator_id']}: "
                f"{data['status']}（{data['path']}）"
            )
        elif event.kind == "warning":
            creator = f"{data.get('creator_id')}: " if data.get("creator_id") else ""
            self.progress.console.print(f"[yellow]{creator}{data['message']}[/yellow]")
        elif event.kind == "job_finished":
            if data.get("dry_run"):
                self.progress.console.print("[cyan]預覽完成，未下載投稿或資源。[/cyan]")
            else:
                self.progress.console.print(
                    f"完成：成功 {data['success']}，內容未變 {data['unchanged']}，"
                    f"未完成 {data['failure']}"
                )


def _run_backup(
    settings: AppConfig, *, creators: tuple[str, ...], posts: tuple[str, ...],
    dry_run: bool, max_posts: int | None, browser: str | None, scope: str,
    include_profile: bool, include_fancard: bool,
) -> None:
    with Progress(
        SpinnerColumn(), TextColumn("{task.description}"), TextColumn("{task.completed} 項"),
        console=console, disable=not console.is_terminal, transient=True,
    ) as progress:
        task = progress.add_task("準備備份", total=None)
        sink = RichBackupEventSink(progress, task)
        BackupUseCase(settings, sink=sink).run(BackupRequest(
            creators=creators,
            posts=posts,
            dry_run=dry_run,
            max_posts=max_posts,
            browser=browser,
            scope=scope,
            include_profile=include_profile,
            include_fancard=include_fancard,
        ))


@app.command()
def backup(
    creator: Annotated[list[str] | None, typer.Option("--creator", help="指定 Creator ID 或首頁網址；可重複使用")] = None,
    post: Annotated[list[str] | None, typer.Option("--post", help="指定 Post ID 或投稿網址；可重複使用")] = None,
    fancard: Annotated[bool, typer.Option("--fancard", help="同時保存指定創作者當月份 Fan Card")] = False,
    profile: Annotated[bool, typer.Option("--profile", help="同時保存指定創作者的 Creator Profile")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="只查詢並顯示備份計畫，不下載投稿或資源")] = False,
    max_posts: Annotated[int | None, typer.Option("--max-posts", min=1, max=100, help="覆寫本次實際下載上限")] = None,
    browser: Annotated[str | None, typer.Option("--browser", help="從指定瀏覽器讀取 FANBOX Cookie，例如 chrome")] = None,
    config: Annotated[Path, typer.Option("--config", "-c", help="設定檔路徑")] = Path("config.yaml"),
) -> None:
    """唯一下載入口；備份全部支援中創作者、指定創作者或指定投稿。"""
    settings = load_config(config)
    try:
        creators = tuple(dict.fromkeys(FanboxClient.creator_id(value) for value in (creator or [])))
        posts = tuple(dict.fromkeys(
            value.strip() if value.strip().isdigit() else FanboxClient.post_id_from_url(value)
            for value in (post or [])
        ))
        if creators and posts:
            raise ValueError("--creator 與 --post 不可同時使用")
        if (fancard or profile) and not creators:
            raise ValueError("--fancard 與 --profile 只能搭配 --creator 使用")
        scope = (
            f"posts:{','.join(posts)}" if posts else
            f"creators:{','.join(creators)}" if creators else "supporting"
        )
        _run_backup(
            settings, creators=creators, posts=posts, dry_run=dry_run,
            max_posts=max_posts, browser=browser, scope=scope,
            include_profile=profile if creators else True,
            include_fancard=fancard if creators else True,
        )
    except ValueError as exc:
        console.print(f"[red]備份參數錯誤：[/red]{exc}")
        raise typer.Exit(2) from exc
    except Exception as exc:
        handle_remote_error(exc)


@app.command()
def verify(
    config: Annotated[Path, typer.Option("--config", "-c", help="設定檔路徑")] = Path("config.yaml"),
) -> None:
    """以檔案大小與 SHA-256 驗證已完成的本機資源。"""
    issues = ArchiveService(load_config(config)).verify()
    if not issues:
        console.print("[green]完整性驗證通過。[/green]")
        return
    for issue in issues:
        console.print(f"[red]{issue.reason}[/red] {issue.path}")
    raise typer.Exit(1)


@app.command("index")
def build_index(
    force: Annotated[bool, typer.Option("--force", help="忽略頁面指紋並完整重建索引")] = False,
    check: Annotated[bool, typer.Option("--check", help="只驗證現有索引，不重建")] = False,
    config: Annotated[Path, typer.Option("--config", "-c", help="設定檔路徑")] = Path("config.yaml"),
) -> None:
    """建立或驗證可直接以瀏覽器開啟的離線閱讀索引。"""
    builder = IndexBuilder(load_config(config))
    if check:
        issues = builder.check()
        if not issues:
            console.print("[green]索引驗證通過。[/green]")
            return
        for issue in issues:
            console.print(f"[red]{issue}[/red]")
        raise typer.Exit(1)
    try:
        result = builder.build(force=force)
    except Exception as exc:
        console.print(f"[red]索引建置失敗：[/red]{exc}")
        raise typer.Exit(1) from exc
    console.print(
        f"[green]索引已建立。[/green]產生 {result.rendered} 頁，沿用 {result.reused} 頁，"
        f"警告 {len(result.warnings)} 項。"
    )
    console.print(str(result.index_path))
    for warning in result.warnings:
        console.print(f"[yellow]{warning}[/yellow]")


@app.command()
def serve(
    port: Annotated[int, typer.Option("--port", min=1, max=65535, help="本機閱讀伺服器連接埠")] = 8765,
    open_browser: Annotated[bool, typer.Option("--open/--no-open", help="啟動後以預設瀏覽器開啟")] = True,
    config: Annotated[Path, typer.Option("--config", "-c", help="設定檔路徑")] = Path("config.yaml"),
) -> None:
    """啟動動態本機閱讀器；不需預先執行 index。"""
    settings = load_config(config)
    try:
        import threading

        import uvicorn

        from .webapp import create_app

        url = f"http://127.0.0.1:{port}/"
        if open_browser:
            threading.Timer(0.75, lambda: webbrowser.open(url)).start()
        console.print(f"[green]動態閱讀器已啟動：[/green]{url}")
        console.print("按 Ctrl+C 停止；下載完成後重新整理頁面即可看到新內容。")
        uvicorn.run(
            create_app(settings, config_path=config),
            host="127.0.0.1", port=port, log_level="info",
        )
    except KeyboardInterrupt:
        console.print("\n閱讀器已停止。")
    except Exception as exc:
        console.print(f"[red]閱讀器啟動失敗：[/red]{exc}")
        raise typer.Exit(1) from exc


@app.command("clear-posts")
def clear_posts(
    yes: Annotated[bool, typer.Option("--yes", help="確認永久刪除所有本機 Post 與其版本／資源")] = False,
    config: Annotated[Path, typer.Option("--config", "-c", help="設定檔路徑")] = Path("config.yaml"),
) -> None:
    """清空 Post 舊資料並重設回補進度；保留 Fan Card、創作者與登入資料。"""
    settings = load_config(config)
    if not yes and not typer.confirm("確定永久刪除所有 Post 舊資料？Fan Card 與登入資料會保留"):
        console.print("已取消。")
        raise typer.Exit()
    try:
        count = ArchiveService(settings).clear_posts()
        result = IndexBuilder(settings).build(force=True)
    except Exception as exc:
        console.print(f"[red]清除 Post 失敗：[/red]{exc}")
        raise typer.Exit(1) from exc
    console.print(f"[green]已清除 {count} 篇 Post。[/green]Fan Card、創作者與登入資料均已保留。")
    console.print(f"索引已重建：{result.index_path}")


@app.command("open")
def open_archive(
    post: Annotated[str | None, typer.Option("--post", help="開啟指定投稿 ID 的最新版閱讀頁")] = None,
    version: Annotated[int | None, typer.Option("--version", min=1, help="搭配 --post 開啟指定版本")] = None,
    creator: Annotated[str | None, typer.Option("--creator", help="在索引中篩選指定 Creator ID")] = None,
    fancard: Annotated[str | None, typer.Option("--fancard", help="開啟指定 Creator ID 的 Fan Card")] = None,
    month: Annotated[str | None, typer.Option("--month", help="搭配 --fancard 指定 YYYY-MM 月份")] = None,
    folder: Annotated[bool, typer.Option("--folder", help="改以檔案總管開啟對應的備份目錄")] = False,
    config: Annotated[Path, typer.Option("--config", "-c", help="設定檔路徑")] = Path("config.yaml"),
) -> None:
    """以預設瀏覽器開啟本機索引、投稿或 Fan Card。"""
    settings = load_config(config)
    root = settings.storage.output_dir.resolve()
    if version is not None and not post:
        console.print("[red]--version 必須搭配 --post。[/red]")
        raise typer.Exit(2)
    if month and not fancard:
        console.print("[red]--month 必須搭配 --fancard。[/red]")
        raise typer.Exit(2)
    if post and (creator or fancard):
        console.print("[red]--post 不能與 --creator 或 --fancard 併用。[/red]")
        raise typer.Exit(2)
    if fancard and creator:
        console.print("[red]--fancard 不能與 --creator 併用。[/red]")
        raise typer.Exit(2)
    if post and not post.isdigit():
        console.print("[red]投稿 ID 必須是數字。[/red]")
        raise typer.Exit(2)
    safe_card_creator = safe_filename(fancard) if fancard else None
    if fancard and (safe_card_creator != fancard or not month or len(month) != 7
                    or month[4] != "-" or not month.replace("-", "").isdigit()):
        console.print("[red]Fan Card 需要安全的 Creator ID 與 --month YYYY-MM。[/red]")
        raise typer.Exit(2)

    if folder:
        target_folder = root
        database = ArchiveService(settings).db
        if post:
            rows = database.version_rows(post)
            selected = next((row for row in rows if version == int(row["version_number"])), None) if version else (rows[-1] if rows else None)
            if selected:
                target_folder = Path(str(selected["local_path"])).resolve()
            else:
                console.print(f"[red]找不到投稿版本：[/red]{post}")
                raise typer.Exit(1)
        elif fancard:
            selected = database.latest_fancard_version(fancard, month or "")
            if selected:
                target_folder = Path(str(selected["local_path"])).resolve()
            else:
                console.print(f"[red]找不到 Fan Card：[/red]{fancard}/{month}")
                raise typer.Exit(1)
        elif creator:
            safe_creator = safe_filename(creator)
            if safe_creator != creator:
                console.print("[red]Creator ID 含有不安全字元。[/red]")
                raise typer.Exit(2)
            target_folder = confined_path(root, Path(safe_creator))
        try:
            target_folder.relative_to(root)
        except ValueError as exc:
            console.print("[red]資料庫中的本機路徑超出備份根目錄。[/red]")
            raise typer.Exit(1) from exc
        if not target_folder.is_dir():
            console.print(f"[red]找不到備份目錄：[/red]{target_folder}")
            raise typer.Exit(1)
        if os.name == "nt":
            os.startfile(target_folder)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target_folder)])
        else:
            subprocess.Popen(["xdg-open", str(target_folder)])
        return

    target = root / "index.html"
    fragment = ""
    if post:
        name = f"v{version:04d}.html" if version else "latest.html"
        target = confined_path(root, Path("_site") / "posts" / post / name)
    elif fancard:
        target = confined_path(root, Path("_site") / "fancards" / str(safe_card_creator) / str(month) / "latest.html")
    elif creator:
        fragment = f"#view=posts&creator={quote(creator, safe='')}"
    if not target.is_file():
        console.print(f"[red]找不到閱讀頁：[/red]{target}")
        console.print("請先執行 `fanbox-archiver index`。")
        raise typer.Exit(1)
    webbrowser.open(target.as_uri() + fragment)


@app.command()
def versions(
    post_id: Annotated[str, typer.Argument(help="投稿 ID")],
    config: Annotated[Path, typer.Option("--config", "-c", help="設定檔路徑")] = Path("config.yaml"),
) -> None:
    """列出某篇投稿已保存的所有版本。"""
    if not post_id.isdigit():
        console.print("[red]投稿 ID 必須是數字。[/red]")
        raise typer.Exit(2)
    rows = ArchiveService(load_config(config)).db.version_rows(post_id)
    if not rows:
        console.print(f"找不到投稿 {post_id} 的版本紀錄。")
        raise typer.Exit(1)
    table = Table("版本", "遠端更新時間", "擷取時間", "狀態", "路徑")
    for row in rows:
        table.add_row(
            f"v{int(row['version_number']):04d}", format_local_time(row["remote_updated_at"]),
            format_local_time(row["captured_at"]), row["status"], row["local_path"],
        )
    console.print(table)


@app.command()
def retry(
    browser: Annotated[str | None, typer.Option("--browser", help="從指定瀏覽器讀取 FANBOX Cookie，例如 chrome")] = None,
    config: Annotated[Path, typer.Option("--config", "-c", help="設定檔路徑")] = Path("config.yaml"),
) -> None:
    """重新處理資料庫中含失敗、遺失或損壞資源的投稿。"""
    try:
        settings = load_config(config)
        cookie = get_cookie(settings, browser)
    except Exception as exc:
        handle_remote_error(exc)
        return
    service = ArchiveService(settings, cookie=cookie)
    versions_to_retry = service.db.retryable_versions()
    if not versions_to_retry:
        console.print("沒有需要重試的版本或資源。")
        return
    for row in versions_to_retry:
        post_id = str(row["post_id"])
        try:
            metadata = Path(str(row["json_path"] or ""))
            if not metadata.exists():
                metadata = Path(str(row["local_path"])) / "post.json"
            post = Post.model_validate_json(metadata.read_text(encoding="utf-8"))
            status = service.save(post, download_assets=True, force=True)
            console.print(f"{post_id}/v{int(row['version_number']):04d}: {status.value}")
        except Exception as exc:
            console.print(f"[red]{post_id}/v{int(row['version_number']):04d}: {exc}[/red]")


@app.command()
def status(
    config: Annotated[Path, typer.Option("--config", "-c", help="設定檔路徑")] = Path("config.yaml"),
) -> None:
    """顯示本機備份資料庫統計。"""
    database = ArchiveService(load_config(config)).db
    stats = database.statistics()
    if not stats:
        console.print("尚無備份紀錄。")
    else:
        table = Table("項目", "數量", title="FANBOX Archiver")
        for key, value in sorted(stats.items()):
            table.add_row(key, str(value))
        console.print(table)
    run = database.latest_run()
    if run:
        run_kind = "預覽" if run["dry_run"] else "備份"
        console.print(
            f"最後執行（{run_kind}）：{format_local_time(run['finished_at'] or run['started_at'])}｜範圍 {run['scope']}｜"
            f"成功 {run['success_count']}｜失敗 {run['failure_count']}"
        )
    successful = database.latest_successful_run()
    if successful:
        console.print(f"最後成功備份：{format_local_time(successful['finished_at'])}｜範圍 {successful['scope']}")
    failures = database.recent_failures()
    if failures:
        failure_table = Table("Post ID", "創作者", "狀態", "錯誤", title="最近失敗")
        for row in failures:
            failure_table.add_row(row["post_id"], row["creator_id"], row["status"], row["last_error"] or "-")
        console.print(failure_table)
    incomplete = database.incomplete_creator_rows()
    if incomplete:
        creator_table = Table("Creator ID", "名稱", "回補游標", "最近檢查", "錯誤", title="尚未完成歷史回補")
        for row in incomplete:
            creator_table.add_row(
                row["creator_id"], row["name"], row["backfill_cursor"] or "起點",
                format_local_time(row["last_recent_check_at"]), row["last_error"] or "-",
            )
        console.print(creator_table)
