from __future__ import annotations

import os
from datetime import UTC, datetime
import json
import sqlite3
import sys
import webbrowser
from pathlib import Path
from typing import Annotated

import click
import typer
import yaml
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
from .config import AppConfig
from .credentials import cookie_header
from .models import Post
from .parser import HtmlPostParser
from .service import ArchiveService
from .application import (
    AuthenticationService, BackupEvent, BackupJobManager, BackupRequest, BackupScheduler, BackupUseCase,
)
from .archive_lock import ArchiveLock
from .database import Database
from .diagnostics import open_folder
from .windows_task import DESKTOP_EXE_ENV, refresh_wake_task
from .logging_setup import configure_logging, get_logger
from .legacy_site import cleanup_owned_archive
from .audit import ArchiveAuditor, ArchiveRepairer
from .security import confined_path, safe_filename
from .timestamps import isoformat_display, set_display_timezone
from .i18n import (
    BASE_LOCALE, LANGUAGE_SETTINGS, Translator, error_text, localize, resolve_locale, system_locales,
    translate,
)


if os.name == "nt":
    # Python may inherit cp950 on Traditional-Chinese Windows even though FANBOX
    # titles commonly contain Japanese characters.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

# Help texts are written in the base language at import time and swapped for the chosen
# language just before parsing (see ``localize_help``); this maps each text back to its key.
_HELP_KEYS: dict[str, str] = {}


def _h(key: str) -> str:
    text = translate(key)
    assert _HELP_KEYS.setdefault(text, key) == key, f"{key} repeats the text of {_HELP_KEYS[text]}"
    return text


# Messages follow ``--lang``, then config.yaml ``display.language`` once loaded. ``_run_locale``
# is what the command line chose before parsing; every invocation starts again from it.
_run_locale = BASE_LOCALE
_translator = Translator(BASE_LOCALE)


def tr(key: str, /, **params: object) -> str:
    return _translator(key, **params)


def shown(value: object) -> str:
    """Core text (``Text``) in this run's language; other values as they are."""
    return str(localize(value, _translator.locale))


def _set_locale(locale: str) -> None:
    global _translator
    _translator = Translator(locale)


def localize_help(command: click.Command, locale: str) -> click.Command:
    """Show ``--help`` of ``command`` (built by Typer) and all its subcommands in ``locale``."""
    translator = Translator(locale)

    def swap(text: str | None) -> str | None:
        key = _HELP_KEYS.get(text or "")
        return translator(key) if key else text

    command.help = swap(command.help)
    for param in command.params:
        if hasattr(param, "help"):
            param.help = swap(param.help)
    for child in getattr(command, "commands", {}).values():
        localize_help(child, locale)
    return command


def localized_command(locale: str) -> click.Command:
    """The CLI as a click command with its help in ``locale`` (also used by the tests)."""
    return localize_help(typer.main.get_command(app), locale)


def _argv_locale(argv: list[str]) -> str:
    """The language of this run before any parsing: ``--lang``, else config.yaml, else the system."""
    def option(*names: str) -> str | None:
        for index, item in enumerate(argv):
            for name in names:
                if item == name and index + 1 < len(argv):
                    return argv[index + 1]
                if item.startswith(f"{name}="):
                    return item.split("=", 1)[1]
        return None

    setting = option("--lang")
    if setting not in LANGUAGE_SETTINGS:
        setting = "auto"
        try:
            data = yaml.safe_load(Path(option("--config", "-c") or "config.yaml").read_text(encoding="utf-8"))
            configured = (data or {}).get("display", {}).get("language")
            if configured in LANGUAGE_SETTINGS:
                setting = configured
        except (OSError, ValueError, AttributeError, yaml.YAMLError):
            pass
    return resolve_locale(setting, system_locales())


class LocalizedTyper(typer.Typer):
    """Picks the language from the command line before Typer builds and parses the commands."""

    def __call__(self, *args, **kwargs):
        argv = kwargs.get("args")
        if argv is None:
            argv = args[0] if args else sys.argv[1:]
        global _run_locale
        locale = _run_locale = _argv_locale(list(argv))
        # As Typer.__call__, but the built command gets its help translated before parsing.
        if sys.excepthook != typer.main.except_hook:
            sys.excepthook = typer.main.except_hook
        return localized_command(locale)(*args, **kwargs)


app = LocalizedTyper(
    name="fanbox-archiver",
    help=_h("cli.help.app"),
    no_args_is_help=True,
)
auth_app = typer.Typer(
    help=_h("cli.help.auth_group"),
    invoke_without_command=True,
)
app.add_typer(auth_app, name="auth")
console = Console()
# ``--lang`` overrides ``display.language`` for one invocation (e.g. ``--lang qps-ploc``).
_language_override: str | None = None


@app.callback()
def main(
    lang: Annotated[str | None, typer.Option(
        "--lang", help=_h("cli.help.lang"),
    )] = None,
) -> None:
    global _language_override
    if lang is not None and lang not in LANGUAGE_SETTINGS:
        raise typer.BadParameter(tr("cli.lang_unsupported", lang=lang), param_hint="--lang")
    _language_override = lang
    _set_locale(resolve_locale(lang, system_locales()) if lang is not None else _run_locale)


def translator(settings: AppConfig) -> Translator:
    return Translator(resolve_locale(_language_override or settings.display.language, system_locales()))


def _use_translator(settings: AppConfig) -> None:
    _set_locale(translator(settings).locale)


def format_local_time(value: object) -> str:
    return isoformat_display(value)


def load_config(path: Path) -> AppConfig:
    try:
        settings = AppConfig.load(path)
        configure_logging(settings)
        set_display_timezone(settings.display.timezone)
        _use_translator(settings)
        return settings
    except (OSError, ValidationError) as exc:
        console.print(f"[red]{tr('cli.config_error')}[/red]{exc}")
        raise typer.Exit(2) from exc


def handle_remote_error(exc: Exception) -> None:
    get_logger().error("%s: %s", type(exc).__name__, exc)
    console.print(f"[red]{shown(error_text(exc))}[/red]")
    raise typer.Exit(1) from exc


def get_cookie(settings: AppConfig, browser: str | None = None) -> str:
    return cookie_header(
        browser,
        profile_dir=None if browser else settings.auth.profile_dir,
        browser_channel=settings.auth.browser_channel,
    )


def verify_login(settings: AppConfig, browser: str | None = None) -> None:
    if browser is None:
        status = AuthenticationService(settings).check()
        if status.state == "authenticated":
            console.print(f"[green]{tr('cli.auth.valid')}[/green]")
            return
        console.print(f"[red]{shown(status.message)}[/red]")
        raise typer.Exit(1)
    cookie = get_cookie(settings, browser)
    if not cookie:
        console.print(f"[yellow]{tr('cli.auth.no_session')}[/yellow]")
        raise typer.Exit(1)
    with FanboxClient(
        cookie=cookie, timeout=settings.download.timeout_seconds,
        request_interval=settings.download.request_interval_seconds,
    ) as client:
        ok = client.verify_auth()
    console.print(f"[green]{tr('cli.auth.valid')}[/green]" if ok else f"[red]{tr('cli.auth.invalid')}[/red]")


@auth_app.callback(help=_h("cli.help.cmd_auth"))
def auth(
    ctx: typer.Context,
    browser: Annotated[str | None, typer.Option("--browser", help=_h("cli.help.browser"))] = None,
    config: Annotated[Path, typer.Option("--config", "-c", help=_h("cli.help.config"))] = Path("config.yaml"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    settings = load_config(config)
    try:
        verify_login(settings, browser)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_remote_error(exc)


@auth_app.command("check", help=_h("cli.help.cmd_auth_check"))
def auth_check(
    browser: Annotated[str | None, typer.Option("--browser", help=_h("cli.help.browser"))] = None,
    config: Annotated[Path, typer.Option("--config", "-c", help=_h("cli.help.config"))] = Path("config.yaml"),
) -> None:
    settings = load_config(config)
    try:
        verify_login(settings, browser)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_remote_error(exc)


@auth_app.command("login", help=_h("cli.help.cmd_auth_login"))
def auth_login(
    timeout_minutes: Annotated[int, typer.Option("--timeout-minutes", min=1, max=30, help=_h("cli.help.timeout_minutes"))] = 10,
    config: Annotated[Path, typer.Option("--config", "-c", help=_h("cli.help.config"))] = Path("config.yaml"),
) -> None:
    settings = load_config(config)
    console.print(f"[cyan]{tr('cli.auth.login_prompt')}[/cyan]")
    console.print(tr("cli.auth.login_privacy"))
    try:
        AuthenticationService(settings).login(
            timeout_seconds=timeout_minutes * 60,
        )
        verify_login(settings)
    except Exception as exc:
        handle_remote_error(exc)


@app.command(help=_h("cli.help.cmd_creators"))
def creators(
    refresh: Annotated[bool, typer.Option("--refresh", help=_h("cli.help.refresh"))] = False,
    json_output: Annotated[bool, typer.Option("--json", help=_h("cli.help.creators_json"))] = False,
    browser: Annotated[str | None, typer.Option("--browser", help=_h("cli.help.browser"))] = None,
    config: Annotated[Path, typer.Option("--config", "-c", help=_h("cli.help.config"))] = Path("config.yaml"),
) -> None:
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
    table = Table("Creator ID", tr("cli.creators.column_name"), tr("cli.creators.column_posts"),
                  tr("cli.creators.column_last_sync"), tr("cli.creators.column_status"), tr("cli.creators.column_url"))
    for row in rows:
        table.add_row(
            str(row["creator_id"]), str(row["name"]), str(row["post_count"]),
            format_local_time(row["last_sync"]), shown(row["status"]), str(row["url"]),
        )
    console.print(table)


@app.command("import-html", help=_h("cli.help.cmd_import_html"))
def import_html(
    html: Annotated[Path, typer.Argument(help=_h("cli.help.html"))],
    source_url: Annotated[str | None, typer.Option("--url", help=_h("cli.help.source_url"))] = None,
    download_assets: Annotated[bool, typer.Option("--download-assets/--metadata-only", help=_h("cli.help.download_assets"))] = False,
    force: Annotated[bool, typer.Option("--force", help=_h("cli.help.force"))] = False,
    config: Annotated[Path, typer.Option("--config", "-c", help=_h("cli.help.config"))] = Path("config.yaml"),
) -> None:
    settings = load_config(config)
    try:
        post = HtmlPostParser().parse_file(html, source_url)
        status = save_with_progress(
            ArchiveService(settings), post, download_assets=download_assets, force=force
        )
    except Exception as exc:
        console.print(f"[red]{tr('cli.import.failed')}[/red]{shown(error_text(exc))}")
        raise typer.Exit(1) from exc
    console.print(f"[green]{tr('cli.import.done')}[/green] {post.post_id}：{post.title}（{status.value}）")


def _print_plan(data: dict) -> None:
    table = Table("Creator ID", "Profile", tr("cli.backup.column_discovered"),
                  tr("cli.backup.column_new_updated_retry"), tr("cli.backup.column_skipped"))
    for scan in data["scans"]:
        table.add_row(
            scan["creator_id"], str(scan.get("profile") or "-"), str(scan["discovered"]),
            f"{scan['new']}/{scan['updated']}/{scan['retry']}",
            str(scan["skipped"]),
        )
    console.print(table)
    console.print(tr(
        "cli.backup.plan_total", new=data["new"], updated=data["updated"], retried=data["retried"],
        skipped=data["skipped"], deferred=data["deferred"],
    ))


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
                description=tr("cli.backup.profile_started", creator_id=data["creator_id"]),
            )
        elif event.kind == "profile_finished":
            preview = tr("cli.backup.preview_suffix") if data.get("dry_run") else ""
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
                self.progress.console.print(f"[cyan]{tr('cli.backup.preview_done')}[/cyan]")
            else:
                self.progress.console.print(tr(
                    "cli.backup.done", success=data["success"], unchanged=data["unchanged"],
                    failure=data["failure"],
                ))


def _run_backup(
    settings: AppConfig, *, creators: tuple[str, ...], posts: tuple[str, ...],
    dry_run: bool, max_posts: int | None, browser: str | None, scope: str,
    include_profile: bool, include_fancard: bool,
) -> None:
    with Progress(
        SpinnerColumn(), TextColumn("{task.description}"), TextColumn(tr("cli.backup.items", count="{task.completed}")),
        console=console, disable=not console.is_terminal, transient=True,
    ) as progress:
        task = progress.add_task(tr("cli.backup.preparing"), total=None)
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


@app.command(help=_h("cli.help.cmd_backup"))
def backup(
    creator: Annotated[list[str] | None, typer.Option("--creator", help=_h("cli.help.backup_creator"))] = None,
    post: Annotated[list[str] | None, typer.Option("--post", help=_h("cli.help.backup_post"))] = None,
    fancard: Annotated[bool, typer.Option("--fancard", help=_h("cli.help.backup_fancard"))] = False,
    profile: Annotated[bool, typer.Option("--profile", help=_h("cli.help.backup_profile"))] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help=_h("cli.help.dry_run"))] = False,
    max_posts: Annotated[int | None, typer.Option("--max-posts", min=1, max=100, help=_h("cli.help.max_posts"))] = None,
    browser: Annotated[str | None, typer.Option("--browser", help=_h("cli.help.browser"))] = None,
    config: Annotated[Path, typer.Option("--config", "-c", help=_h("cli.help.config"))] = Path("config.yaml"),
) -> None:
    settings = load_config(config)
    try:
        creators = tuple(dict.fromkeys(FanboxClient.creator_id(value) for value in (creator or [])))
        posts = tuple(dict.fromkeys(
            value.strip() if value.strip().isdigit() else FanboxClient.post_id_from_url(value)
            for value in (post or [])
        ))
        if creators and posts:
            raise ValueError(tr("cli.backup.creator_and_post"))
        if (fancard or profile) and not creators:
            raise ValueError(tr("cli.backup.extras_need_creator"))
        scope = (
            f"posts:{','.join(posts)}" if posts else
            f"creators:{','.join(creators)}" if creators else "supporting"
        )
        if not dry_run:
            cleanup_owned_archive(settings)
        _run_backup(
            settings, creators=creators, posts=posts, dry_run=dry_run,
            max_posts=max_posts, browser=browser, scope=scope,
            include_profile=profile if creators else True,
            include_fancard=fancard if creators else True,
        )
    except ValueError as exc:
        console.print(f"[red]{tr('cli.backup.bad_arguments')}[/red]{shown(error_text(exc))}")
        raise typer.Exit(2) from exc
    except Exception as exc:
        handle_remote_error(exc)


@app.command(help=_h("cli.help.cmd_verify"))
def verify(
    config: Annotated[Path, typer.Option("--config", "-c", help=_h("cli.help.config"))] = Path("config.yaml"),
) -> None:
    issues = ArchiveService(load_config(config)).verify()
    if not issues:
        console.print(f"[green]{tr('cli.verify.passed')}[/green]")
        return
    for issue in issues:
        console.print(f"[red]{shown(issue.reason)}[/red] {issue.path}")
    raise typer.Exit(1)


@app.command(help=_h("cli.help.cmd_audit"))
def audit(
    json_output: Annotated[
        bool, typer.Option("--json", help=_h("cli.help.audit_json"))
    ] = False,
    config: Annotated[Path, typer.Option("--config", "-c", help=_h("cli.help.config"))] = Path("config.yaml"),
) -> None:
    try:
        settings = AppConfig.load(config)
        set_display_timezone(settings.display.timezone)
        _use_translator(settings)
    except (OSError, ValidationError) as exc:
        console.print(f"[red]{tr('cli.config_error')}[/red]{exc}")
        raise typer.Exit(2) from exc
    report = ArchiveAuditor(settings).run()
    if json_output:
        console.print_json(data=report.model_dump(mode="json"))
    else:
        info_count = report.finding_count - report.blocking_count
        console.print(tr(
            "cli.audit.summary", blocking=report.blocking_count, automatic=report.automatic_count,
            info=info_count,
        ))
        for finding in report.findings:
            if finding.severity == "info":
                continue
            console.print(
                f"[red]{finding.code}[/red] {finding.subject_type}/{finding.subject_id} "
                f"{finding.issue} {finding.evidence}"
            )
    if report.blocking_count:
        raise typer.Exit(1)


@app.command("schedule-run", help=_h("cli.help.cmd_schedule_run"))
def schedule_run(
    config: Annotated[Path, typer.Option("--config", "-c", help=_h("cli.help.config"))] = Path("config.yaml"),
) -> None:
    settings = load_config(config)
    log = get_logger()
    if not settings.schedule.enabled:
        log.info("自動備份未啟用，略過背景排程檢查。")
        return
    lock = ArchiveLock(settings.storage.output_dir)
    if not lock.try_acquire():
        # The desktop app (or another background run) owns this archive and schedules itself.
        log.info("封存正由 FANBOX Archiver 使用中，略過本次背景排程檢查。")
        return
    cleanup_owned_archive(settings, lock)
    manager = BackupJobManager(settings, archive_lock=lock)
    try:
        scheduler = BackupScheduler(
            lambda: settings, lambda: manager, Database(settings.storage.database),
        )
        outcome = scheduler.tick()
        try:
            refresh_wake_task(settings, config, os.environ.get(DESKTOP_EXE_ENV), now=datetime.now(UTC))
        except (OSError, RuntimeError) as exc:
            log.warning("無法更新喚醒排程：%s", exc)
        if outcome != "submitted":
            log.info("沒有到期的排程備份。")
            return
        job_id = scheduler.status()["last_job"]["job_id"]
        job = manager.wait(job_id, timeout=12 * 60 * 60)
        log.info("背景排程備份結束：%s", job["status"])
        if job["status"] != "completed":
            raise typer.Exit(1)
    finally:
        manager.close()


@app.command("repair-copy", help=_h("cli.help.cmd_repair_copy"))
def repair_copy(
    output: Annotated[Path, typer.Option("--output", help=_h("cli.help.repair_output"))],
    config: Annotated[Path, typer.Option("--config", "-c", help=_h("cli.help.config"))] = Path("config.yaml"),
) -> None:
    try:
        settings = AppConfig.load(config)
        set_display_timezone(settings.display.timezone)
        _use_translator(settings)
        result = ArchiveRepairer(settings).repair_copy(output)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        console.print(f"[red]{tr('cli.repair.failed')}[/red]{shown(error_text(exc))}")
        raise typer.Exit(1) from exc
    console.print(f"[green]{tr('cli.repair.created')}[/green]" + tr(
        "cli.repair.summary", applied=result.applied_actions, remaining=result.remaining_findings,
        unrecoverable=result.unrecoverable_findings,
    ))
    console.print(tr("cli.repair.database_backup", path=str(result.database_backup)), markup=False)
    console.print(tr("cli.repair.report", path=str(result.report), count=result.verify_issue_count), markup=False)


@app.command("index", hidden=True, help=_h("cli.help.cmd_index"))
def build_index(
    force: Annotated[bool, typer.Option("--force", hidden=True)] = False,
    check: Annotated[bool, typer.Option("--check", hidden=True)] = False,
    config: Annotated[Path, typer.Option("--config", "-c", hidden=True)] = Path("config.yaml"),
) -> None:
    # Kept only so old scripts and scheduled tasks get a clear message instead of "no such command".
    del force, check, config
    console.print(f"[red]{tr('cli.index.removed')}[/red]")
    console.print(tr("cli.index.alternative"))
    raise typer.Exit(1)


@app.command(help=_h("cli.help.cmd_serve"))
def serve(
    port: Annotated[int, typer.Option("--port", min=1, max=65535, help=_h("cli.help.port"))] = 8765,
    open_browser: Annotated[bool, typer.Option("--open/--no-open", help=_h("cli.help.open_browser"))] = True,
    config: Annotated[Path, typer.Option("--config", "-c", help=_h("cli.help.config"))] = Path("config.yaml"),
) -> None:
    settings = load_config(config)
    try:
        import threading

        import uvicorn

        from .webapp import create_app

        url = f"http://127.0.0.1:{port}/"
        if open_browser:
            threading.Timer(0.75, lambda: webbrowser.open(url)).start()
        console.print(f"[green]{tr('cli.serve.started')}[/green]{url}")
        console.print(tr("cli.serve.hint"))
        uvicorn.run(
            create_app(settings, config_path=config, run_scheduler=True),
            host="127.0.0.1", port=port, log_level="info",
        )
    except KeyboardInterrupt:
        console.print("\n" + tr("cli.serve.stopped"))
    except Exception as exc:
        console.print(f"[red]{tr('cli.serve.failed')}[/red]{shown(error_text(exc))}")
        raise typer.Exit(1) from exc


@app.command("clear-posts", help=_h("cli.help.cmd_clear_posts"))
def clear_posts(
    yes: Annotated[bool, typer.Option("--yes", help=_h("cli.help.clear_yes"))] = False,
    config: Annotated[Path, typer.Option("--config", "-c", help=_h("cli.help.config"))] = Path("config.yaml"),
) -> None:
    settings = load_config(config)
    if not yes and not typer.confirm(tr("cli.clear.confirm")):
        console.print(tr("cli.clear.cancelled"))
        raise typer.Exit()
    try:
        cleanup_owned_archive(settings)
        count = ArchiveService(settings).clear_posts()
    except Exception as exc:
        console.print(f"[red]{tr('cli.clear.failed')}[/red]{shown(error_text(exc))}")
        raise typer.Exit(1) from exc
    console.print(f"[green]{tr('cli.clear.done', count=count)}[/green]{tr('cli.clear.kept')}")


@app.command("open", help=_h("cli.help.cmd_open"))
def open_archive(
    post: Annotated[str | None, typer.Option("--post", help=_h("cli.help.open_post"))] = None,
    version: Annotated[int | None, typer.Option("--version", min=1, help=_h("cli.help.open_version"))] = None,
    creator: Annotated[str | None, typer.Option("--creator", help=_h("cli.help.open_creator"))] = None,
    fancard: Annotated[str | None, typer.Option("--fancard", help=_h("cli.help.open_fancard"))] = None,
    month: Annotated[str | None, typer.Option("--month", help=_h("cli.help.open_month"))] = None,
    folder: Annotated[bool, typer.Option("--folder", hidden=True)] = False,
    config: Annotated[Path, typer.Option("--config", "-c", help=_h("cli.help.config"))] = Path("config.yaml"),
) -> None:
    del folder  # folders are the only target since the static site was removed; kept for old scripts
    settings = load_config(config)
    root = settings.storage.output_dir.resolve()
    if version is not None and not post:
        console.print(f"[red]{tr('cli.open.version_needs_post')}[/red]")
        raise typer.Exit(2)
    if month and not fancard:
        console.print(f"[red]{tr('cli.open.month_needs_fancard')}[/red]")
        raise typer.Exit(2)
    if post and (creator or fancard):
        console.print(f"[red]{tr('cli.open.post_exclusive')}[/red]")
        raise typer.Exit(2)
    if fancard and creator:
        console.print(f"[red]{tr('cli.open.fancard_exclusive')}[/red]")
        raise typer.Exit(2)
    if post and not post.isdigit():
        console.print(f"[red]{tr('cli.post_id_numeric')}[/red]")
        raise typer.Exit(2)
    safe_card_creator = safe_filename(fancard) if fancard else None
    if fancard and (safe_card_creator != fancard or not month or len(month) != 7
                    or month[4] != "-" or not month.replace("-", "").isdigit()):
        console.print(f"[red]{tr('cli.open.fancard_arguments')}[/red]")
        raise typer.Exit(2)

    target_folder = root
    database = ArchiveService(settings).db
    if post:
        rows = database.version_rows(post)
        selected = next((row for row in rows if version == int(row["version_number"])), None) if version else (rows[-1] if rows else None)
        if selected:
            target_folder = Path(str(selected["local_path"])).resolve()
        else:
            console.print(f"[red]{tr('cli.open.version_missing')}[/red]{post}")
            raise typer.Exit(1)
    elif fancard:
        selected = database.latest_fancard_version(fancard, month or "")
        if selected:
            target_folder = Path(str(selected["local_path"])).resolve()
        else:
            console.print(f"[red]{tr('cli.open.fancard_missing')}[/red]{fancard}/{month}")
            raise typer.Exit(1)
    elif creator:
        safe_creator = safe_filename(creator)
        if safe_creator != creator:
            console.print(f"[red]{tr('cli.open.unsafe_creator')}[/red]")
            raise typer.Exit(2)
        target_folder = confined_path(root, Path(safe_creator))
    try:
        target_folder.relative_to(root)
    except ValueError as exc:
        console.print(f"[red]{tr('cli.open.outside_root')}[/red]")
        raise typer.Exit(1) from exc
    if not target_folder.is_dir():
        console.print(f"[red]{tr('cli.open.folder_missing')}[/red]{target_folder}")
        raise typer.Exit(1)
    open_folder(target_folder)


@app.command(help=_h("cli.help.cmd_versions"))
def versions(
    post_id: Annotated[str, typer.Argument(help=_h("cli.help.post_id"))],
    config: Annotated[Path, typer.Option("--config", "-c", help=_h("cli.help.config"))] = Path("config.yaml"),
) -> None:
    if not post_id.isdigit():
        console.print(f"[red]{tr('cli.post_id_numeric')}[/red]")
        raise typer.Exit(2)
    rows = ArchiveService(load_config(config)).db.version_rows(post_id)
    if not rows:
        console.print(tr("cli.versions.none", post_id=post_id))
        raise typer.Exit(1)
    table = Table(tr("cli.versions.column_version"), tr("cli.versions.column_remote_updated"),
                  tr("cli.versions.column_captured"), tr("cli.versions.column_status"), tr("cli.versions.column_path"))
    for row in rows:
        table.add_row(
            f"v{int(row['version_number']):04d}", format_local_time(row["remote_updated_at"]),
            format_local_time(row["captured_at"]), row["status"], row["local_path"],
        )
    console.print(table)


@app.command(help=_h("cli.help.cmd_retry"))
def retry(
    browser: Annotated[str | None, typer.Option("--browser", help=_h("cli.help.browser"))] = None,
    config: Annotated[Path, typer.Option("--config", "-c", help=_h("cli.help.config"))] = Path("config.yaml"),
) -> None:
    try:
        settings = load_config(config)
        cookie = get_cookie(settings, browser)
    except Exception as exc:
        handle_remote_error(exc)
        return
    service = ArchiveService(settings, cookie=cookie)
    versions_to_retry = service.db.retryable_versions()
    if not versions_to_retry:
        console.print(tr("cli.retry.none"))
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
            console.print(f"[red]{post_id}/v{int(row['version_number']):04d}: {shown(error_text(exc))}[/red]")


@app.command(help=_h("cli.help.cmd_status"))
def status(
    config: Annotated[Path, typer.Option("--config", "-c", help=_h("cli.help.config"))] = Path("config.yaml"),
) -> None:
    settings = load_config(config)
    t = tr
    database = ArchiveService(settings).db
    stats = database.statistics()
    if not stats:
        console.print(t("cli.status.empty"))
    else:
        # Statistic keys and job statuses are machine-readable and stay untranslated.
        table = Table(t("cli.status.column_item"), t("cli.status.column_count"), title="FANBOX Archiver")
        for key, value in sorted(stats.items()):
            table.add_row(key, str(value))
        console.print(table)
    run = database.latest_run()
    if run:
        console.print(t(
            "cli.status.last_run",
            kind=t("cli.status.kind_preview") if run["dry_run"] else t("cli.status.kind_backup"),
            time=format_local_time(run["finished_at"] or run["started_at"]), scope=run["scope"],
            success=run["success_count"], failure=run["failure_count"],
        ), markup=False)
    successful = database.latest_successful_run()
    if successful:
        console.print(t("cli.status.last_success", time=format_local_time(successful["finished_at"]),
                        scope=successful["scope"]), markup=False)
    failures = database.recent_failures()
    if failures:
        failure_table = Table("Post ID", t("cli.status.column_creator"), t("cli.status.column_status"),
                              t("cli.status.column_error"), title=t("cli.status.failures_title"))
        for row in failures:
            failure_table.add_row(row["post_id"], row["creator_id"], row["status"], row["last_error"] or "-")
        console.print(failure_table)
    incomplete = database.incomplete_creator_rows()
    if incomplete:
        creator_table = Table("Creator ID", t("cli.status.column_name"), t("cli.status.column_cursor"),
                              t("cli.status.column_checked"), t("cli.status.column_error"),
                              title=t("cli.status.incomplete_title"))
        for row in incomplete:
            creator_table.add_row(
                row["creator_id"], row["name"], row["backfill_cursor"] or t("cli.status.cursor_start"),
                format_local_time(row["last_recent_check_at"]), row["last_error"] or "-",
            )
        console.print(creator_table)
