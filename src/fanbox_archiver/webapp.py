from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import MutableHeaders
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import AppConfig
from . import __version__
from .application import BackupJobManager, BackupRequest
from .client import FanboxClient
from .reader import ArchiveReader, ReaderNotFound


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
    markdown: MarkdownConfigPatch | None = None
    logging: LoggingConfigPatch | None = None


def create_app(config: AppConfig, *, config_path: Path | None = None) -> FastAPI:
    reader = ArchiveReader(config)
    jobs = BackupJobManager(config)
    session_token = secrets.token_urlsafe(32)
    assets = Path(__file__).with_name("web_assets")
    home_html = (assets / "index.html").read_text(encoding="utf-8").replace(
        "__FANBOX_SESSION_TOKEN__", session_token
    )
    app = FastAPI(title="FANBOX Archiver", version=__version__)
    app.state.reader = reader
    app.state.jobs = jobs
    app.state.session_token = session_token
    app.state.config = config
    app.state.config_path = config_path.resolve() if config_path else None
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "test"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/", include_in_schema=False)
    async def home():
        return HTMLResponse(home_html)

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
            raise HTTPException(status_code=403, detail="工作階段權杖無效")

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
        }

    @app.patch("/api/config", dependencies=[Depends(require_mutation_token)])
    async def patch_config(body: ConfigPatch):
        if app.state.config_path is None:
            raise HTTPException(status_code=409, detail="伺服器未指定可寫入的設定檔")
        if app.state.jobs.has_active():
            raise HTTPException(status_code=409, detail="工作執行期間無法修改設定")
        patch = body.model_dump(exclude_none=True)
        try:
            updated = app.state.config.with_editable_patch(patch)
            AppConfig.save_editable(app.state.config_path, updated, patch)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        app.state.config = updated
        app.state.jobs.config = updated
        return {"editable": updated.editable_dict(), "saved": True}

    @app.get("/api/jobs")
    async def list_jobs():
        return {"items": app.state.jobs.list()}

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str):
        job = app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="找不到工作")
        return job

    @app.post("/api/jobs/backup", status_code=202, dependencies=[Depends(require_mutation_token)])
    async def start_backup(body: BackupJobBody):
        try:
            raw_creators = [*body.creators]
            if body.creator:
                raw_creators.append(body.creator)
            creators = tuple(dict.fromkeys(
                FanboxClient.creator_id(value) for value in raw_creators
            ))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
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
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/jobs/verify", status_code=202, dependencies=[Depends(require_mutation_token)])
    async def start_verify():
        try:
            return app.state.jobs.submit_verify()
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/api/jobs/{job_id}/cancel", dependencies=[Depends(require_mutation_token)]
    )
    async def cancel_job(job_id: str):
        try:
            job = app.state.jobs.cancel(job_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if job is None:
            raise HTTPException(status_code=404, detail="找不到工作")
        return job

    @app.post(
        "/api/jobs/{job_id}/retry", status_code=202,
        dependencies=[Depends(require_mutation_token)],
    )
    async def retry_job(job_id: str):
        try:
            job = app.state.jobs.retry(job_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if job is None:
            raise HTTPException(status_code=404, detail="找不到工作")
        return job

    @app.get("/api/creators")
    async def creators():
        return {"items": reader.list_creators()}

    @app.get("/api/creators/{creator_id}")
    async def creator(creator_id: str):
        try:
            return reader.creator(creator_id)
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/creators/{creator_id}/avatar")
    async def creator_avatar(creator_id: str):
        try:
            item = reader.creator_avatar(creator_id)
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
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
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/creators/{creator_id}/profile/versions")
    async def creator_profile_versions(creator_id: str):
        try:
            return {"items": reader.creator_profile_versions(creator_id)}
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/creators/{creator_id}/profile/versions/{version}/cover")
    async def creator_profile_cover(creator_id: str, version: int):
        try:
            item = reader.creator_profile_cover(creator_id, version)
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
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
            raise HTTPException(status_code=404, detail=str(exc)) from exc
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
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/fancards/{creator_id}/{target_month}/versions/{version}/image")
    async def fancard_image(creator_id: str, target_month: str, version: int):
        try:
            item = reader.fancard_image(creator_id, target_month, version)
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(
            item.path, media_type=item.media_type, filename=item.filename,
            content_disposition_type="inline",
        )

    @app.get("/api/posts")
    async def posts(
        page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
        q: str = Query("", max_length=200), creator: str = Query("", max_length=200),
        status: str = Query("", max_length=40), tag: str = Query("", max_length=200),
    ):
        return reader.list_posts(
            page=page, page_size=page_size, query=q.strip(),
            creator=creator.strip(), status=status.strip(), tag=tag.strip(),
        )

    @app.get("/api/posts/{post_id}")
    async def post(
        post_id: str, version: int | None = Query(None, ge=1),
        creator: str = Query("", max_length=200), q: str = Query("", max_length=200),
        tag: str = Query("", max_length=200),
    ):
        try:
            item = reader.post(post_id, version=version)
            item["navigation"] = reader.post_navigation(
                post_id, creator=creator.strip(), query=q.strip(), tag=tag.strip(),
            )
            return item
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/posts/{post_id}/versions/{version}/media/{asset_id}")
    async def media(post_id: str, version: int, asset_id: str):
        try:
            item = reader.media(post_id, version, asset_id)
        except ReaderNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        disposition = "inline" if item.media_type.startswith(("image/", "video/", "audio/")) else "attachment"
        return FileResponse(
            item.path, media_type=item.media_type, filename=item.filename,
            content_disposition_type=disposition,
        )

    return app
