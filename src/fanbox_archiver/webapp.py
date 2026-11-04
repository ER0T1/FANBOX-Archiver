from __future__ import annotations

import os
import secrets
from contextvars import ContextVar
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.datastructures import MutableHeaders
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import AppConfig, ScheduleConfig, ThemeColors
from .theme import THEME_COLOR_KEYS, THEME_DEFAULTS, custom_theme_css
from .i18n import BASE_LOCALE, LanguageSetting, Text, browser_script, error_text, localize, resolve_locale
from . import __version__
from .application import (
    AuthenticationJobManager, AuthenticationService, BackupJobManager, BackupRequest,
    BackupScheduler,
)
from .archive_lock import ArchiveLock
from .legacy_site import LegacySiteCleanup, cleanup_owned_archive
from .database import Database
from . import diagnostics
from .diagnostics import FolderTarget
from .schedule import describe, upcoming
from .timestamps import (
    COMMON_TIMEZONES, display_zone, resolve_timezone, set_display_timezone, timezone_names,
)
from .windows_task import DESKTOP_EXE_ENV, sync_background_schedule
from .client import FanboxClient
from .reader import ArchiveReader, ReaderNotFound


# The language of the request being answered: interface text in JSON responses (``Text`` from
# the core, e.g. sign-in status, schedule summary, error details) is shown in it.
_RESPONSE_LOCALE: ContextVar[str] = ContextVar("fanbox_response_locale", default=BASE_LOCALE)


class LocalizedJSONResponse(JSONResponse):
    def render(self, content: object) -> bytes:
        return super().render(localize(content, _RESPONSE_LOCALE.get()))


class SecurityHeadersMiddleware:
    """Add local-reader security headers without buffering response bodies."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                headers["X-Frame-Options"] = "DENY"
                headers["Content-Security-Policy"] = (
                    "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                    "script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
                )
                if scope.get("path", "").startswith("/api/") or scope.get("path") == "/":
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BackupJobBody(BaseModel):
    creator: str | None = Field(default=None, max_length=200)
    creators: list[Annotated[str, Field(max_length=200)]] = Field(
        default_factory=list, max_length=100
    )
    dry_run: bool = False
    max_posts: int | None = Field(default=None, ge=1, le=100)
    mode: Literal["full", "profile", "fancard"] = "full"
    include_profile: bool = True
    include_fancard: bool = True


class DownloadConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_images: bool | None = None
    download_attachments: bool | None = None
    download_cover: bool | None = None
    retry_count: int | None = Field(None, ge=0, le=10)
    request_interval_seconds: float | None = Field(None, ge=1.0)
    resume: bool | None = None
    verify_sha256: bool | None = None
    timeout_seconds: float | None = Field(None, ge=5.0, le=600.0)


class SyncConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skip_completed: bool | None = None
    check_updates: bool | None = None
    preserve_deleted_posts: bool | None = None
    max_posts_per_run: int | None = Field(None, ge=1, le=100)
    supporting_only: bool | None = None
    rotate_creators: bool | None = None
    recent_unchanged_stop_count: int | None = Field(None, ge=1, le=500)


class BackupDefaultsConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dry_run: bool | None = None
    include_profile: bool | None = None
    include_fancard: bool | None = None


class MarkdownConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    yaml_front_matter: bool | None = None
    relative_image_paths: bool | None = None
    preserve_original_order: bool | None = None


class ScheduleConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    frequency: Literal["daily", "weekly", "monthly"] | None = None
    interval: int | None = Field(None, ge=1, le=30)
    weekday: int | None = Field(None, ge=0, le=6)
    month_day: int | None = Field(None, ge=1, le=31)
    time: str | None = Field(None, max_length=5)
    start_date: date | None = None
    creators: list[Annotated[str, Field(max_length=200)]] | None = Field(None, max_length=100)
    power: Literal["no_wake_battery_ok", "no_wake_ac_only", "wake"] | None = None


class DisplayConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str | None = Field(None, max_length=64)
    theme: Literal["system", "dark", "light"] | None = None
    language: LanguageSetting | None = None
    colors: ThemeColors | None = None


class LoggingConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: str | None = None
    write_to_file: bool | None = None
    keep_days: int | None = Field(None, ge=1, le=365)


class ConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    download: DownloadConfigPatch | None = None
    sync: SyncConfigPatch | None = None
    backup_defaults: BackupDefaultsConfigPatch | None = None
    schedule: ScheduleConfigPatch | None = None
    display: DisplayConfigPatch | None = None
    markdown: MarkdownConfigPatch | None = None
    logging: LoggingConfigPatch | None = None


class LoginBody(BaseModel):
    timeout_seconds: int = Field(default=600, ge=60, le=1800)


class OpenFolderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: FolderTarget


def problem_text(exc: Exception) -> object:
    """A settings problem for the UI: the validator's own (translatable) message, not pydantic's wrapper."""
    if isinstance(exc, ValidationError):
        messages: list[object] = []
        for item in exc.errors():
            original = (item.get("ctx") or {}).get("error")
            messages.append(error_text(original) if isinstance(original, BaseException) else item.get("msg", ""))
        return messages[0] if len(messages) == 1 else messages
    return error_text(exc)


def create_app(
    config: AppConfig, *, config_path: Path | None = None, run_scheduler: bool = False,
) -> FastAPI:
    set_display_timezone(config.display.timezone)
    reader = ArchiveReader(config)
    # A real server owns its archive so the background scheduled backup never writes alongside it.
    jobs = BackupJobManager(
        config, archive_lock=ArchiveLock(config.storage.output_dir) if run_scheduler else None,
    )
    auth_service = AuthenticationService(config)
    auth_jobs = AuthenticationJobManager(auth_service)
    session_token = secrets.token_urlsafe(32)
    assets = Path(__file__).with_name("web_assets")
    home_html = (assets / "index.html").read_text(encoding="utf-8").replace(
        "__FANBOX_SESSION_TOKEN__", session_token
    )

    def display_info() -> dict:
        zone = display_zone()
        system = zone if zone.setting == "system" else resolve_timezone("system")
        return {"setting": zone.setting, "timezone": zone.name, "notice": zone.notice,
                "system_timezone": system.name}
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Only a real server runs the background schedule; test clients never start it.
        if run_scheduler:
            app.state.scheduler.start()
            # Re-sync on every start so an upgrade or moved install keeps the task correct.
            await run_in_threadpool(sync_background)
            # Remove the old static site once this server owns the archive and nothing is running;
            # otherwise the next start tries again.
            if not app.state.jobs.has_active():
                app.state.legacy_site = await run_in_threadpool(
                    cleanup_owned_archive, app.state.config, app.state.jobs.archive_lock,
                )
        try:
            yield
        finally:
            app.state.scheduler.stop()

    async def response_language(request: Request) -> None:
        # Runs in the request's own task, so the response rendered later sees this value.
        _RESPONSE_LOCALE.set(request_locale(request))

    app = FastAPI(
        title="FANBOX Archiver", version=__version__, lifespan=lifespan,
        default_response_class=LocalizedJSONResponse, dependencies=[Depends(response_language)],
    )

    @app.exception_handler(StarletteHTTPException)
    async def localized_http_error(request: Request, exc: StarletteHTTPException):
        detail = localize(exc.detail, request_locale(request))
        if isinstance(detail, list):  # several validation problems (see problem_text)
            detail = "；".join(str(item) for item in detail)
        return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))
    app.state.reader = reader
    app.state.jobs = jobs
    app.state.auth_service = auth_service
    app.state.auth_jobs = auth_jobs
    # Last real check, kept as a state name and time only (never cookies or tokens).
    app.state.last_auth = None
    app.state.session_token = session_token
    app.state.config = config
    app.state.config_path = config_path.resolve() if config_path else None
    app.state.legacy_site = LegacySiteCleanup()
    app.state.background = {"state": "unavailable", "message": Text("schedule.background_unavailable")}

    def sync_background() -> None:
        app.state.background = sync_background_schedule(
            app.state.config, app.state.config_path, os.environ.get(DESKTOP_EXE_ENV),
            now=datetime.now(UTC),
        )

    app.state.scheduler = BackupScheduler(
        lambda: app.state.config, lambda: app.state.jobs, Database(config.storage.database),
        is_busy=lambda: app.state.auth_jobs.active() is not None,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "test"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/", include_in_schema=False)
    async def home(request: Request):
        # Zone, theme and language are read per request so a saved change applies on reload.
        return HTMLResponse(home_html.replace("__FANBOX_TIMEZONE__", display_zone().name)
                            .replace("__FANBOX_THEME__", app.state.config.display.css_theme)
                            .replace("__FANBOX_LANG__", request_locale(request)))

    def request_locale(request: Request) -> str:
        # ``auto`` follows the browser (WebView2 sends the Windows display language).
        header = request.headers.get("accept-language", "")
        preferred = [part.split(";", 1)[0] for part in header.split(",")]
        return resolve_locale(app.state.config.display.language, preferred)

    @app.get("/i18n.js", include_in_schema=False)
    async def i18n_script(request: Request):
        return Response(browser_script(request_locale(request)), media_type="text/javascript",
                        headers={"Cache-Control": "no-store"})

    @app.get("/theme.css", include_in_schema=False)
    async def theme_css():
        colors = app.state.config.display.colors
        return Response(custom_theme_css(colors.light, colors.dark), media_type="text/css",
                        headers={"Cache-Control": "no-store"})

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/status")
    async def status():
        return reader.status()

    def require_mutation_token(
        token: Annotated[str | None, Header(alias="X-Fanbox-Token")] = None,
    ) -> None:
        if token is None or not secrets.compare_digest(token, session_token):
            raise HTTPException(status_code=403, detail=Text("server.token_invalid"))

    @app.get("/api/config")
    async def get_config():
        current = app.state.config
        return {
            "editable": current.editable_dict(),
            "storage": {
                "output_dir": str(current.storage.output_dir),
                "database": str(current.storage.database),
            },
            "config_path": str(app.state.config_path) if app.state.config_path else None,
            "writable": app.state.config_path is not None,
            "display": display_info(),
            "timezones": {"common": list(COMMON_TIMEZONES), "all": list(timezone_names())},
            "theme_colors": {"keys": list(THEME_COLOR_KEYS), "defaults": THEME_DEFAULTS},
        }

    def remember_auth(state: str) -> None:
        app.state.last_auth = {"state": state, "checked_at": datetime.now(UTC).isoformat()}

    @app.get("/api/auth/status", dependencies=[Depends(require_mutation_token)])
    async def auth_status():
        active = app.state.auth_jobs.active()
        if active:
            return {
                "state": "checking", "source": "profile",
                "message": Text("server.auth_login_waiting"),
                "can_login": False, "can_logout": False,
                "externally_managed": False, "job": active,
            }
        if app.state.jobs.has_active():
            return {
                "state": "locked", "source": "profile",
                "message": Text("server.auth_locked"),
                "can_login": False, "can_logout": False,
                "externally_managed": False, "job": None,
                "last_known": app.state.last_auth,
            }
        status = await run_in_threadpool(app.state.auth_service.check)
        remember_auth(status.state)
        return {**status.as_dict(), "job": None, "last_known": None}

    @app.post(
        "/api/auth/login", status_code=202,
        dependencies=[Depends(require_mutation_token)],
    )
    async def auth_login(body: LoginBody):
        if app.state.jobs.has_active():
            raise HTTPException(status_code=409, detail=Text("server.login_blocked"))
        try:
            return app.state.auth_jobs.start(timeout_seconds=body.timeout_seconds)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=error_text(exc)) from exc

    @app.get(
        "/api/auth/login/{job_id}", dependencies=[Depends(require_mutation_token)]
    )
    async def auth_login_job(job_id: str):
        job = app.state.auth_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=Text("server.login_job_missing"))
        return job

    @app.post(
        "/api/auth/login/{job_id}/cancel",
        dependencies=[Depends(require_mutation_token)],
    )
    async def auth_login_cancel(job_id: str):
        job = app.state.auth_jobs.cancel(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=Text("server.login_job_missing"))
        return job

    @app.post("/api/auth/logout", dependencies=[Depends(require_mutation_token)])
    async def auth_logout():
        if app.state.jobs.has_active() or app.state.auth_jobs.active():
            raise HTTPException(status_code=409, detail=Text("server.logout_blocked"))
        try:
            status = await run_in_threadpool(app.state.auth_service.logout)
            remember_auth(status.state)
            return status.as_dict()
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=error_text(exc)) from exc

    @app.patch("/api/config", dependencies=[Depends(require_mutation_token)])
    async def patch_config(body: ConfigPatch):
        if app.state.config_path is None:
            raise HTTPException(status_code=409, detail=Text("server.config_not_writable"))
        if app.state.jobs.has_active():
            raise HTTPException(status_code=409, detail=Text("server.config_blocked"))
        patch = body.model_dump(exclude_none=True)
        try:
            if "schedule" in patch:
                patch["schedule"] = normalize_schedule_patch(patch["schedule"])
            updated = app.state.config.with_editable_patch(patch)
            if updated.schedule.enabled and updated.schedule.start_date is None:
                # N-day / N-week cycles count from the day the schedule is switched on.
                patch["schedule"]["start_date"] = datetime.now(display_zone().tz).date()
                updated = app.state.config.with_editable_patch(patch)
            AppConfig.save_editable(app.state.config_path, updated, patch)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=problem_text(exc)) from exc
        schedule_changed = updated.schedule != app.state.config.schedule
        timezone_changed = updated.display != app.state.config.display
        app.state.config = updated
        app.state.jobs.config = updated
        if timezone_changed:
            set_display_timezone(updated.display.timezone)
        if schedule_changed or timezone_changed:
            # Schedule times are read in the display zone: count from now so a
            # reinterpretation never re-runs or "misses" an occurrence.
            await run_in_threadpool(app.state.scheduler.reset)
            await run_in_threadpool(sync_background)
        return {"editable": updated.editable_dict(), "display": display_info(), "saved": True}

    @app.get("/api/diagnostics", dependencies=[Depends(require_mutation_token)])
    async def get_diagnostics():
        return await run_in_threadpool(diagnostics.collect, app.state.config, app.state.config_path,
                                       app.state.legacy_site.notices)

    @app.post("/api/diagnostics/open", dependencies=[Depends(require_mutation_token)])
    async def open_diagnostics_folder(body: OpenFolderBody):
        path = diagnostics.folder_path(app.state.config, body.target)
        if path is None:
            raise HTTPException(status_code=404, detail=Text("server.desktop_logs_only"))
        if not path.is_dir():
            raise HTTPException(status_code=404, detail=Text("server.folder_missing"))
        if not diagnostics.can_open_folders():
            raise HTTPException(status_code=501, detail=Text("server.folder_unsupported"))
        await run_in_threadpool(diagnostics.open_folder, path)
        return {"opened": body.target}

    def normalize_schedule_patch(values: dict) -> dict:
        if "creators" in values:
            values["creators"] = list(dict.fromkeys(
                FanboxClient.creator_id(value) for value in values["creators"]
            ))
        return values

    @app.get("/api/schedule")
    async def schedule_status():
        status = await run_in_threadpool(app.state.scheduler.status)
        return {**status, "background": app.state.background}

    @app.post("/api/schedule/preview", dependencies=[Depends(require_mutation_token)])
    async def schedule_preview(body: ScheduleConfigPatch):
        values = normalize_schedule_patch(body.model_dump(exclude_none=True))
        try:
            schedule = ScheduleConfig.model_validate({**app.state.config.schedule.model_dump(), **values})
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=problem_text(exc)) from exc
        if schedule.start_date is None:
            schedule.start_date = datetime.now(display_zone().tz).date()
        runs = upcoming(schedule, datetime.now(UTC), 3)
        return {"summary": describe(schedule), "next_runs": [item.isoformat() for item in runs]}

    @app.post("/api/schedule/run", status_code=202, dependencies=[Depends(require_mutation_token)])
    async def schedule_run_now():
        try:
            return await run_in_threadpool(app.state.scheduler.run_now)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=error_text(exc)) from exc

    @app.get("/api/jobs")
    async def list_jobs(
        page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
        kind: Literal["backup", "verify"] | None = None,
        status: Literal["queued", "running", "cancelling", "completed", "failed", "cancelled", "interrupted"] | None = None,
        order: Literal["desc", "asc"] = "desc",
    ):
        return await run_in_threadpool(
            app.state.jobs.page, kind=kind, status=status, ascending=order == "asc",
            page=page, page_size=page_size,
        )

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str):
        job = app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=Text("server.job_missing"))
        return job

    @app.post("/api/jobs/backup", status_code=202, dependencies=[Depends(require_mutation_token)])
    async def start_backup(body: BackupJobBody):
        if app.state.auth_jobs.active():
            raise HTTPException(status_code=409, detail=Text("server.backup_blocked_by_login"))
        try:
            raw_creators = [*body.creators]
            if body.creator:
                raw_creators.append(body.creator)
            creators = tuple(dict.fromkeys(
                FanboxClient.creator_id(value) for value in raw_creators
            ))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=error_text(exc)) from exc
        try:
            base_scope = (
                "supporting" if not creators else
                f"creator:{creators[0]}" if len(creators) == 1 else
                f"creators:{','.join(creators)}"
            )
            return app.state.jobs.submit(BackupRequest(
                creators=creators,
                dry_run=body.dry_run,
                max_posts=body.max_posts,
                scope=(base_scope if body.mode == "full" else f"{base_scope}:{body.mode}"),
                mode=body.mode,
                include_profile=body.include_profile,
                include_fancard=body.include_fancard,
            ))
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=error_text(exc)) from exc

    @app.post("/api/jobs/verify", status_code=202, dependencies=[Depends(require_mutation_token)])
    async def start_verify():
        if app.state.auth_jobs.active():
            raise HTTPException(status_code=409, detail=Text("server.verify_blocked_by_login"))
        try:
            return app.state.jobs.submit_verify()
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=error_text(exc)) from exc

    @app.post(
        "/api/jobs/{job_id}/cancel", dependencies=[Depends(require_mutation_token)]
    )
    async def cancel_job(job_id: str):
        try:
            job = app.state.jobs.cancel(job_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=error_text(exc)) from exc
        if job is None:
            raise HTTPException(status_code=404, detail=Text("server.job_missing"))
        return job

    @app.post(
        "/api/jobs/{job_id}/retry", status_code=202,
        dependencies=[Depends(require_mutation_token)],
    )
    async def retry_job(job_id: str):
        try:
            job = app.state.jobs.retry(job_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=error_text(exc)) from exc
        if job is None:
            raise HTTPException(status_code=404, detail=Text("server.job_missing"))
        return job

    @app.get("/api/creators")
    async def creators():
        return {"items": reader.list_creators()}

    @app.get("/api/creators/{creator_id}")
    async def creator(creator_id: str):
        try:
            return reader.creator(creator_id)
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=error_text(exc)) from exc

    @app.get("/api/creators/{creator_id}/avatar")
    async def creator_avatar(creator_id: str):
        try:
            item = reader.creator_avatar(creator_id)
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=error_text(exc)) from exc
        return FileResponse(
            item.path, media_type=item.media_type, filename=item.filename,
            content_disposition_type="inline",
        )

    @app.get("/api/creators/{creator_id}/profile")
    async def creator_profile(
        creator_id: str, version: int | None = Query(None, ge=1),
    ):
        try:
            return reader.creator_profile(creator_id, version=version)
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=error_text(exc)) from exc

    @app.get("/api/creators/{creator_id}/profile/versions")
    async def creator_profile_versions(creator_id: str):
        try:
            return {"items": reader.creator_profile_versions(creator_id)}
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=error_text(exc)) from exc

    @app.get("/api/creators/{creator_id}/profile/versions/{version}/cover")
    async def creator_profile_cover(creator_id: str, version: int):
        try:
            item = reader.creator_profile_cover(creator_id, version)
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=error_text(exc)) from exc
        return FileResponse(
            item.path, media_type=item.media_type, filename=item.filename,
            content_disposition_type="inline",
        )

    @app.get("/api/creators/{creator_id}/profile/versions/{version}/items/{item_index}/image")
    async def creator_profile_item_image(
        creator_id: str, version: int, item_index: int,
    ):
        try:
            item = reader.creator_profile_item_image(creator_id, version, item_index)
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=error_text(exc)) from exc
        return FileResponse(
            item.path, media_type=item.media_type, filename=item.filename,
            content_disposition_type="inline",
        )

    @app.get("/api/fancards")
    async def fancards(
        q: str = Query("", max_length=200), creator: str = Query("", max_length=200),
    ):
        return {"items": reader.list_fancards(query=q.strip(), creator=creator.strip())}

    @app.get("/api/fancards/{creator_id}/{target_month}")
    async def fancard(
        creator_id: str, target_month: str, version: int | None = Query(None, ge=1),
    ):
        try:
            return reader.fancard(creator_id, target_month, version=version)
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=error_text(exc)) from exc

    @app.get("/api/fancards/{creator_id}/{target_month}/versions/{version}/image")
    async def fancard_image(creator_id: str, target_month: str, version: int):
        try:
            item = reader.fancard_image(creator_id, target_month, version)
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=error_text(exc)) from exc
        return FileResponse(
            item.path, media_type=item.media_type, filename=item.filename,
            content_disposition_type="inline",
        )

    @app.get("/api/posts")
    async def posts(
        page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
        q: str = Query("", max_length=200), creator: str = Query("", max_length=200),
        status: str = Query("", max_length=40), tag: str = Query("", max_length=200),
        order: Literal["desc", "asc"] = "desc",
    ):
        return reader.list_posts(
            page=page, page_size=page_size, query=q.strip(),
            creator=creator.strip(), status=status.strip(), tag=tag.strip(),
            ascending=order == "asc",
        )

    @app.get("/api/posts/{post_id}")
    async def post(
        post_id: str, version: int | None = Query(None, ge=1),
        creator: str = Query("", max_length=200), q: str = Query("", max_length=200),
        tag: str = Query("", max_length=200), order: Literal["desc", "asc"] = "desc",
    ):
        try:
            item = reader.post(post_id, version=version)
            item["navigation"] = reader.post_navigation(
                post_id, creator=creator.strip(), query=q.strip(), tag=tag.strip(),
                ascending=order == "asc",
            )
            return item
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=error_text(exc)) from exc

    @app.get("/api/posts/{post_id}/versions/{version}/media/{asset_id}")
    async def media(post_id: str, version: int, asset_id: str):
        try:
            item = reader.media(post_id, version, asset_id)
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=error_text(exc)) from exc
        disposition = "inline" if item.media_type.startswith(("image/", "video/", "audio/")) else "attachment"
        return FileResponse(
            item.path, media_type=item.media_type, filename=item.filename,
            content_disposition_type=disposition,
        )

    return app
