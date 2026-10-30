from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, Literal

from ..browser_session import BrowserPostSession, profile_auth_material
from ..client import AccessRestrictedError, AuthenticationError, FanboxClient, RateLimitedError
from ..config import AppConfig
from ..credentials import cookie_header
from ..downloader import DownloadAuthorizationError, DownloadRateLimitedError
from ..logging_setup import get_logger
from ..service import ArchiveService
from ..syncing import CreatorScan, SyncCancelled, SyncPlan, SyncResult, SyncService, SyncStopped
from .events import BackupCancelled, BackupEvent, CancellationToken, EventSink, NullEventSink


@dataclass(frozen=True, slots=True)
class BackupRequest:
    creator: str | None = None
    creators: tuple[str, ...] = ()
    posts: tuple[str, ...] = ()
    dry_run: bool = False
    max_posts: int | None = None
    browser: str | None = None
    scope: str = "supporting"
    mode: Literal["full", "profile", "fancard"] = "full"
    include_profile: bool | None = None
    include_fancard: bool | None = None


@dataclass(frozen=True, slots=True)
class BackupOutcome:
    run_id: int
    plan: SyncPlan
    result: SyncResult | None
    dry_run: bool


class BackupUseCase:
    """Interface-neutral backup orchestration shared by CLI and future jobs."""

    def __init__(
        self, config: AppConfig, *, sink: EventSink | None = None,
        cancellation: CancellationToken | None = None,
    ) -> None:
        self.config = config
        self.sink = sink or NullEventSink()
        self.cancellation = cancellation or CancellationToken()

    def run(self, request: BackupRequest) -> BackupOutcome:
        self.cancellation.raise_if_cancelled()
        use_profile, cookie, user_agent = self._auth_material(request.browser)
        archive = ArchiveService(self.config, cookie=cookie, user_agent=user_agent)
        run_id = 0 if request.dry_run else archive.db.begin_run(request.scope)
        self._emit(
            "job_started", run_id=run_id, scope=request.scope,
            dry_run=request.dry_run, mode=request.mode,
        )
        get_logger().info(
            "backup run %s started scope=%s dry_run=%s",
            run_id, request.scope, request.dry_run,
        )
        plan: SyncPlan | None = None
        result: SyncResult | None = None
        finished = False
        try:
            self.cancellation.raise_if_cancelled()
            with FanboxClient(
                cookie=cookie,
                timeout=self.config.download.timeout_seconds,
                user_agent=user_agent,
                request_interval=self.config.download.request_interval_seconds,
            ) as client:
                client.parse_warning_callback = lambda post_id, message: self._emit(
                    "warning", post_id=post_id, message=message,
                )
                syncing = SyncService(client, archive, mutate=not request.dry_run)
                requested_creators = request.creators or ((request.creator,) if request.creator else ())
                selected_posts: dict[str, Any] = {}
                if request.posts:
                    planning_session = (
                        BrowserPostSession(
                            self.config.auth.profile_dir,
                            channel=self.config.auth.browser_channel,
                            request_interval=self.config.download.request_interval_seconds,
                        )
                        if use_profile else nullcontext(None)
                    )
                    with planning_session as post_session:
                        if post_session is not None:
                            client.post_payload_fetcher = post_session.fetch
                        plan, selected_posts = syncing.plan_posts(request.posts, request.max_posts)
                        client.post_payload_fetcher = None
                    creators = []
                else:
                    creators = syncing.resolve_creators(requested_creators or None)
                    plan = (
                        syncing.plan(creators, request.max_posts or self.config.sync.max_posts_per_run)
                        if request.mode == "full" else self._metadata_plan(creators)
                    )
                for warning in plan.warnings:
                    self._emit("warning", message=warning)
                include_profile = request.mode == "profile" or (
                    request.mode == "full"
                    and (request.include_profile if request.include_profile is not None else True)
                    and not request.posts
                )
                include_fancard = request.mode == "fancard" or (
                    request.mode == "full"
                    and (request.include_fancard if request.include_fancard is not None else True)
                    and not request.posts
                )
                profile_results = (
                    self._archive_profiles(creators, client, archive, dry_run=request.dry_run)
                    if include_profile else {}
                )
                self._emit(
                    "plan_ready", mode=request.mode,
                    **self._plan_data(plan, profile_results),
                )
                if request.dry_run:
                    finished = True
                    self._emit("job_finished", run_id=run_id, dry_run=True, success=0, failure=0)
                    return BackupOutcome(run_id, plan, None, True)

                if not plan.selected and not include_fancard:
                    if request.mode == "full" and not request.posts:
                        result = syncing.execute(
                            plan, should_cancel=lambda: self.cancellation.cancelled,
                        )
                    self._finish(archive, run_id, plan, result)
                    finished = True
                    self._emit(
                        "job_finished", run_id=run_id, dry_run=False,
                        success=0, unchanged=0, failure=0, mode=request.mode,
                    )
                    return BackupOutcome(run_id, plan, None, False)

                if include_fancard and not use_profile:
                    raise RuntimeError("單獨拉取 Fan Card 需要先以專用瀏覽器完成登入")

                needs_session = use_profile and (
                    include_fancard or (bool(plan.selected) and not selected_posts)
                )
                session_context = (
                    BrowserPostSession(
                        self.config.auth.profile_dir,
                        channel=self.config.auth.browser_channel,
                        request_interval=self.config.download.request_interval_seconds,
                    )
                    if needs_session else nullcontext(None)
                )
                with session_context as post_session:
                    if post_session is not None:
                        if plan.selected and not selected_posts:
                            client.post_payload_fetcher = post_session.fetch
                        if include_fancard:
                            self._archive_fancards(creators, post_session, archive)

                    if plan.selected:
                        def resource_progress(asset: Any, downloaded: int, total: int | None) -> None:
                            self._emit(
                                "asset_progress",
                                asset_id=str(getattr(asset, "asset_id", "resource")),
                                name=str(getattr(asset, "original_name", None) or getattr(asset, "asset_id", "resource")),
                                downloaded=downloaded,
                                total=total,
                            )

                        def item_finished(item: Any, status: Any, unchanged: bool) -> None:
                            self._emit(
                                "item_finished",
                                creator_id=item.creator_id,
                                post_id=item.summary.post_id,
                                status=(type(status).__name__ if isinstance(status, Exception) else status.value),
                                error=str(status) if isinstance(status, Exception) else None,
                                unchanged=unchanged,
                            )

                        archive.progress_callback = resource_progress
                        try:
                            execute = syncing.execute_posts if selected_posts else syncing.execute
                            execute_args = (plan, selected_posts) if selected_posts else (plan,)
                            result = execute(
                                *execute_args, on_item=item_finished,
                                should_cancel=lambda: self.cancellation.cancelled,
                            )
                        finally:
                            archive.progress_callback = None
                    elif request.mode == "full" and not request.posts:
                        result = syncing.execute(
                            plan, should_cancel=lambda: self.cancellation.cancelled,
                        )

            self._finish(archive, run_id, plan, result)
            finished = True
            self._emit(
                "job_finished", run_id=run_id, dry_run=False,
                success=result.success if result else 0,
                unchanged=result.unchanged if result else 0,
                failure=result.failure if result else 0,
                mode=request.mode,
            )
            get_logger().info(
                "backup run %s finished success=%s unchanged=%s failure=%s",
                run_id, result.success if result else 0,
                result.unchanged if result else 0, result.failure if result else 0,
            )
            return BackupOutcome(run_id, plan, result, False)
        except SyncStopped as stopped:
            result = stopped.result
            plan = result.plan
            self._finish(archive, run_id, plan, result)
            finished = True
            self._emit("job_failed", run_id=run_id, error=str(stopped.reason))
            raise stopped.reason
        except SyncCancelled as stopped:
            result = stopped.result
            plan = result.plan
            self._finish(archive, run_id, plan, result)
            finished = True
            self._emit("job_cancelled", run_id=run_id)
            raise BackupCancelled("備份已由使用者取消") from stopped
        except BackupCancelled:
            if not finished and not request.dry_run:
                self._finish_failure(archive, run_id, plan, result)
            self._emit("job_cancelled", run_id=run_id)
            raise
        except Exception as exc:
            if not finished and not request.dry_run:
                self._finish_failure(archive, run_id, plan, result)
            self._emit("job_failed", run_id=run_id, error=str(exc))
            raise

    def _archive_profiles(
        self, creators: list[Any], client: Any, archive: ArchiveService, *, dry_run: bool,
    ) -> dict[str, str]:
        results: dict[str, str] = {}
        fetch = getattr(client, "creator_profile", None)
        if not callable(fetch):
            return results
        for creator in creators:
            self.cancellation.raise_if_cancelled()
            self._emit("profile_started", creator_id=creator.creator_id)
            try:
                profile = fetch(creator.creator_id)
                for message in profile.parse_warnings:
                    self._emit(
                        "profile_warning", creator_id=creator.creator_id, message=message,
                    )
                status = archive.profile_status(profile)
                path = None
                if not dry_run:
                    status, saved = archive.save_profile(profile)
                    path = str(saved)
                latest = archive.db.latest_profile_version(creator.creator_id)
                if dry_run:
                    version = (
                        int(latest["version_number"]) + (status != "unchanged")
                        if latest else 1
                    )
                else:
                    version = int(latest["version_number"]) if latest else None
                self._emit(
                    "profile_finished", creator_id=creator.creator_id,
                    status=status, version=version, path=path, dry_run=dry_run,
                )
                results[creator.creator_id] = status
            except (
                AuthenticationError, AccessRestrictedError, RateLimitedError,
                DownloadAuthorizationError, DownloadRateLimitedError,
            ):
                raise
            except Exception as exc:
                get_logger().warning(
                    "creator profile archive failed creator_id=%s: %s",
                    creator.creator_id, exc,
                )
                self._emit(
                    "profile_warning", creator_id=creator.creator_id, message=str(exc)
                )
                results[creator.creator_id] = "warning"
        return results

    @staticmethod
    def _metadata_plan(creators: list[Any]) -> SyncPlan:
        creator_ids = [str(creator.creator_id) for creator in creators]
        return SyncPlan(
            creators=creator_ids,
            scans=[CreatorScan(creator_id=creator_id) for creator_id in creator_ids],
            selected=[], discovered=0, new=0, updated=0, retried=0,
            skipped=0, deferred=0, eligible=0,
        )

    def _auth_material(self, browser: str | None) -> tuple[bool, str, str | None]:
        use_profile = browser is None and self.config.auth.profile_dir.exists()
        if use_profile:
            material = profile_auth_material(
                self.config.auth.profile_dir, channel=self.config.auth.browser_channel
            )
            return True, material.cookie_header, material.user_agent
        cookie = cookie_header(
            browser,
            profile_dir=None if browser else self.config.auth.profile_dir,
            browser_channel=self.config.auth.browser_channel,
        )
        return False, cookie, None

    def _archive_fancards(self, creators: list[Any], session: Any, archive: ArchiveService) -> None:
        for creator in creators:
            self.cancellation.raise_if_cancelled()
            try:
                payload = session.fetch_fancard(creator.creator_id)
                body = payload.get("body") or {}
                image_url = str(body.get("supporterCardImageUrl") or "")
                image_data = content_type = None
                if image_url:
                    image_data, content_type = session.fetch_binary(image_url)
                else:
                    self._emit(
                        "warning", creator_id=creator.creator_id,
                        message="創作者未提供自訂 Fan Card 卡面，將只保存方案資料。",
                    )
                status, path = archive.save_fancard(payload, image_data, content_type)
                self._emit(
                    "fancard_finished", creator_id=creator.creator_id,
                    status=status, path=str(path),
                )
            except (AuthenticationError, RateLimitedError):
                raise
            except Exception as exc:
                get_logger().error(
                    "Fan Card archive failed creator_id=%s: %s", creator.creator_id, exc
                )
                self._emit(
                    "warning", creator_id=creator.creator_id,
                    message=f"Fan Card 保存失敗：{exc}",
                )

    def _finish(
        self, archive: ArchiveService, run_id: int,
        plan: SyncPlan, result: SyncResult | None,
    ) -> None:
        archive.db.finish_run(
            run_id,
            result.success if result else 0,
            result.failure if result else 0,
            discovered=plan.discovered,
            new=plan.new,
            updated=plan.updated,
            skipped=plan.skipped + (result.unchanged if result else 0),
            retried=plan.retried,
        )

    def _finish_failure(
        self, archive: ArchiveService, run_id: int,
        plan: SyncPlan | None, result: SyncResult | None,
    ) -> None:
        if plan is None:
            archive.db.finish_run(run_id, 0, 1)
        else:
            self._finish(archive, run_id, plan, result)

    def _emit(self, kind: str, **data: Any) -> None:
        self.sink.emit(BackupEvent(kind, data))

    @staticmethod
    def _plan_data(
        plan: SyncPlan, profile_results: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        profile_results = profile_results or {}
        return {
            "creators": len(plan.creators),
            "creator_ids": plan.creators,
            "scans": [
                {
                    "creator_id": scan.creator_id,
                    "discovered": scan.discovered,
                    "skipped": scan.skipped,
                    "new": sum(item.action == "new" for item in scan.items),
                    "updated": sum(item.action == "updated" for item in scan.items),
                    "retry": sum(item.action == "retry" for item in scan.items),
                    "profile": profile_results.get(scan.creator_id),
                    "eligible": len(scan.items),
                    "pages_scanned": scan.pages_scanned,
                    "available_pages": scan.available_pages,
                    "backfill_cursor_before": scan.backfill_cursor_before,
                    "backfill_completed_before": scan.backfill_completed_before,
                    "stop_reason": scan.stop_reason,
                }
                for scan in plan.scans
            ],
            "discovered": plan.discovered,
            "new": plan.new,
            "updated": plan.updated,
            "retried": plan.retried,
            "skipped": plan.skipped,
            "deferred": plan.deferred,
            "selected": len(plan.selected),
            "requested_max_posts": plan.requested_max_posts,
            "eligible": plan.eligible,
            "pages_scanned": plan.pages_scanned,
            "available_pages": plan.available_pages,
            "backfill_cursor_before": {
                scan.creator_id: scan.backfill_cursor_before for scan in plan.scans
            },
            "backfill_completed_before": {
                scan.creator_id: scan.backfill_completed_before for scan in plan.scans
            },
            "stop_reason": plan.stop_reason,
        }
