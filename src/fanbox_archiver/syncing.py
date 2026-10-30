from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Literal

from .client import (
    AccessRestrictedError,
    AuthenticationError,
    Creator,
    FanboxClient,
    PostSummary,
    RateLimitedError,
    RemoteUnavailableError,
)
from .models import Post, PostStatus
from .downloader import DownloadAuthorizationError, DownloadRateLimitedError
from .service import ArchiveService


SyncAction = Literal["new", "updated", "retry"]
StopReason = Literal[
    "limit_reached", "remote_exhausted", "backfill_completed",
    "unchanged_threshold", "eligible_exhausted",
]


@dataclass(slots=True)
class SyncItem:
    creator_id: str
    summary: PostSummary
    action: SyncAction
    source: Literal["recent", "backfill"]


@dataclass(slots=True)
class BackfillBatch:
    page_index: int
    next_page: int
    actionable_post_ids: list[str] = field(default_factory=list)
    remote_exhausted: bool = False


@dataclass(slots=True)
class CreatorScan:
    creator_id: str
    items: list[SyncItem] = field(default_factory=list)
    discovered: int = 0
    skipped: int = 0
    backfill_page: int | None = None
    next_backfill_page: int | None = None
    backfill_completed: bool = False
    pages_scanned: int = 0
    available_pages: int = 0
    backfill_cursor_before: str | None = None
    backfill_completed_before: bool = False
    stop_reason: StopReason = "eligible_exhausted"
    warnings: list[str] = field(default_factory=list)
    backfill_batches: list[BackfillBatch] = field(default_factory=list)


@dataclass(slots=True)
class SyncPlan:
    creators: list[str]
    scans: list[CreatorScan]
    selected: list[SyncItem]
    discovered: int
    new: int
    updated: int
    retried: int
    skipped: int
    deferred: int
    requested_max_posts: int | None = None
    eligible: int = 0
    pages_scanned: int = 0
    available_pages: int = 0
    stop_reason: StopReason = "eligible_exhausted"
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SyncResult:
    plan: SyncPlan
    success: int = 0
    failure: int = 0
    unchanged: int = 0


class SyncStopped(RuntimeError):
    def __init__(self, result: SyncResult, reason: Exception):
        super().__init__(str(reason))
        self.result = result
        self.reason = reason


class SyncCancelled(RuntimeError):
    def __init__(self, result: SyncResult):
        super().__init__("同步已取消")
        self.result = result


class SyncService:
    """Conservative scheduler behind the shared backup use case."""

    def __init__(self, client: FanboxClient, archive: ArchiveService, *, mutate: bool = True):
        self.client = client
        self.archive = archive
        self.db = archive.db
        self.mutate = mutate

    def supporting_creators(self) -> list[Creator]:
        creators = self.client.supporting_creators()
        if self.mutate:
            self.db.record_supporting_creators([(item.creator_id, item.name) for item in creators])
        return creators

    def resolve_creators(self, requested: Iterable[str] | str | None = None) -> list[Creator]:
        creators = self.supporting_creators()
        if requested is None:
            return creators
        values = [requested] if isinstance(requested, str) else list(requested)
        requested_ids = list(dict.fromkeys(FanboxClient.creator_id(value) for value in values))
        by_id = {item.creator_id: item for item in creators}
        missing = [creator_id for creator_id in requested_ids if creator_id not in by_id]
        if missing:
            raise ValueError(f"{', '.join(missing)} 不在目前支援清單中或帳號無權存取")
        return [by_id[creator_id] for creator_id in requested_ids]

    def plan_posts(
        self, post_ids: Iterable[str], max_posts: int | None = None,
    ) -> tuple[SyncPlan, dict[str, Post]]:
        posts: dict[str, Post] = {}
        scans: dict[str, CreatorScan] = {}
        items: list[SyncItem] = []
        skipped = 0
        counts = {"new": 0, "updated": 0, "retry": 0}
        for post_id in dict.fromkeys(post_ids):
            post = self.client.post(post_id)
            posts[post.post_id] = post
            scan = scans.setdefault(post.creator_id, CreatorScan(creator_id=post.creator_id))
            scan.discovered += 1
            row = self.db.post_row(post.post_id)
            if row is None:
                action: SyncAction = "new"
            elif row["status"] != PostStatus.COMPLETED.value:
                action = "retry"
            elif row["content_fingerprint"] != post.content_fingerprint:
                action = "updated"
            else:
                scan.skipped += 1
                skipped += 1
                continue
            summary = PostSummary(
                post_id=post.post_id,
                updated_at=post.updated_at.isoformat() if post.updated_at else None,
                title=post.title,
                fee_required=post.fee_required,
                is_pinned=bool(post.raw.get("isPinned", False)),
            )
            item = SyncItem(post.creator_id, summary, action, "recent")
            scan.items.append(item)
            items.append(item)
            counts[action] += 1
        limit = len(items) if max_posts is None else max_posts
        selected = items[:limit]
        return SyncPlan(
            creators=list(scans), scans=list(scans.values()), selected=selected,
            discovered=len(posts), new=counts["new"], updated=counts["updated"],
            retried=counts["retry"], skipped=skipped,
            deferred=max(0, len(items) - len(selected)),
            requested_max_posts=max_posts, eligible=len(items),
            stop_reason="limit_reached" if max_posts is not None and len(selected) >= max_posts
            else "eligible_exhausted",
        ), posts

    def execute_posts(
        self, plan: SyncPlan, posts: dict[str, Post], *, on_item=None, should_cancel=None,
    ) -> SyncResult:
        result = SyncResult(plan=plan)
        for item in plan.selected:
            if should_cancel and should_cancel():
                raise SyncCancelled(result)
            try:
                status = self.archive.save(posts[item.summary.post_id], download_assets=True)
                if status == PostStatus.COMPLETED:
                    result.success += 1
                else:
                    result.failure += 1
                if on_item:
                    on_item(item, status, False)
            except Exception as exc:
                result.failure += 1
                if on_item:
                    on_item(item, exc, False)
                if isinstance(exc, (
                    AuthenticationError, RateLimitedError,
                    DownloadAuthorizationError, DownloadRateLimitedError,
                )):
                    raise SyncStopped(result, exc) from exc
        return result

    def plan(self, creators: Iterable[Creator], max_posts: int) -> SyncPlan:
        creator_list = list(creators)
        by_id = {item.creator_id: item for item in creator_list}
        ordered_ids = self.db.ordered_creator_ids(
            list(by_id), rotate=self.archive.config.sync.rotate_creators
        )
        scans = [self._scan_creator(creator_id, max_posts) for creator_id in ordered_ids]

        # Take one candidate from each creator in turn. A prolific creator can no
        # longer consume the complete run before another creator gets a chance.
        queues = [deque(scan.items) for scan in scans]
        selected: list[SyncItem] = []
        while len(selected) < max_posts and any(queues):
            for queue in queues:
                if queue and len(selected) < max_posts:
                    selected.append(queue.popleft())

        all_items = [item for scan in scans for item in scan.items]
        counts = {action: sum(item.action == action for item in all_items)
                  for action in ("new", "updated", "retry")}
        skipped = sum(scan.skipped for scan in scans)
        deferred = max(0, len(all_items) - len(selected))
        if len(selected) >= max_posts:
            stop_reason: StopReason = "limit_reached"
        elif scans and all(scan.stop_reason == "backfill_completed" for scan in scans):
            stop_reason = "backfill_completed"
        elif any(scan.stop_reason == "unchanged_threshold" for scan in scans):
            stop_reason = "unchanged_threshold"
        elif scans and all(scan.stop_reason == "remote_exhausted" for scan in scans):
            stop_reason = "remote_exhausted"
        else:
            stop_reason = "eligible_exhausted"
        return SyncPlan(
            creators=ordered_ids,
            scans=scans,
            selected=selected,
            discovered=sum(scan.discovered for scan in scans),
            new=counts["new"],
            updated=counts["updated"],
            retried=counts["retry"],
            skipped=skipped,
            deferred=deferred,
            requested_max_posts=max_posts,
            eligible=len(all_items),
            pages_scanned=sum(scan.pages_scanned for scan in scans),
            available_pages=sum(scan.available_pages for scan in scans),
            stop_reason=stop_reason,
            warnings=[warning for scan in scans for warning in scan.warnings],
        )

    def execute(self, plan: SyncPlan, *, on_item=None, should_cancel=None) -> SyncResult:
        result = SyncResult(plan=plan)
        completed_ids: set[tuple[str, str]] = set()
        downloads = 0
        limit = len(plan.selected)
        for item in self._round_robin_all(plan.scans):
            if should_cancel and should_cancel():
                raise SyncCancelled(result)
            if downloads >= limit:
                break
            try:
                post = self.client.post(item.summary.post_id)
                previous = self.db.post_row(post.post_id)
                if (previous and previous["status"] == PostStatus.COMPLETED.value
                        and previous["content_fingerprint"] == post.content_fingerprint):
                    self.db.set_post_status(post.post_id, PostStatus.COMPLETED)
                    result.unchanged += 1
                    completed_ids.add((item.creator_id, post.post_id))
                    if on_item:
                        on_item(item, PostStatus.COMPLETED, True)
                    continue
                downloads += 1
                status = self.archive.save(post, download_assets=True)
                if status == PostStatus.COMPLETED:
                    result.success += 1
                    completed_ids.add((item.creator_id, post.post_id))
                else:
                    result.failure += 1
                if on_item:
                    on_item(item, status, False)
            except Exception as exc:
                result.failure += 1
                self.db.update_creator_sync(item.creator_id, error=str(exc))
                if on_item:
                    on_item(item, exc, False)
                if isinstance(exc, AccessRestrictedError):
                    self.db.record_post_access_issue(
                        item.creator_id, item.summary, PostStatus.RESTRICTED, str(exc)
                    )
                    continue
                if isinstance(exc, RemoteUnavailableError):
                    self.db.record_post_access_issue(
                        item.creator_id, item.summary, PostStatus.UNAVAILABLE, str(exc)
                    )
                    continue
                if isinstance(exc, (
                    AuthenticationError, RateLimitedError,
                    DownloadAuthorizationError, DownloadRateLimitedError,
                )):
                    raise SyncStopped(result, exc) from exc

        for scan in plan.scans:
            self.db.update_creator_sync(scan.creator_id, recent_checked=True,
                                        success=any(cid == scan.creator_id for cid, _ in completed_ids))
            next_cursor: int | None = None
            completed = False
            for batch in scan.backfill_batches:
                if not all(
                    (scan.creator_id, post_id) in completed_ids
                    for post_id in batch.actionable_post_ids
                ):
                    break
                next_cursor = batch.next_page
                completed = batch.remote_exhausted
            if completed:
                self.db.update_creator_sync(scan.creator_id, backfill_completed=True)
            elif next_cursor is not None:
                self.db.update_creator_sync(
                    scan.creator_id, backfill_cursor=str(next_cursor),
                    backfill_completed=False,
                )
            elif not scan.backfill_batches and scan.stop_reason == "remote_exhausted":
                self.db.update_creator_sync(scan.creator_id, backfill_completed=True)
        return result

    def _scan_creator(self, creator_id: str, max_posts: int) -> CreatorScan:
        pages = self.client.creator_post_pages(creator_id)
        state = self.db.creator_state(creator_id)
        cursor_before = str(state["backfill_cursor"]) if state and state["backfill_cursor"] else None
        completed_before = bool(state and state["backfill_completed"])
        scan = CreatorScan(
            creator_id=creator_id, available_pages=len(pages),
            backfill_cursor_before=cursor_before,
            backfill_completed_before=completed_before,
        )
        if not pages:
            scan.backfill_completed = True
            scan.stop_reason = "remote_exhausted"
            return scan

        seen: set[str] = set()
        recent_unchanged = 0
        scan.pages_scanned = 1
        for summary in self.client.creator_page(pages[0]):
            scan.discovered += 1
            seen.add(summary.post_id)
            item = self._classify(creator_id, summary, "recent")
            if item is None:
                scan.skipped += 1
                recent_unchanged += 1
                if recent_unchanged >= self.archive.config.sync.recent_unchanged_stop_count:
                    scan.stop_reason = "unchanged_threshold"
                    return scan
            else:
                recent_unchanged = 0
                scan.items.append(item)

        if len(scan.items) >= max_posts:
            scan.stop_reason = "limit_reached"
            return scan

        completed = completed_before
        if completed and cursor_before is None:
            scan.backfill_completed = True
            scan.stop_reason = "backfill_completed"
            return scan

        if completed and cursor_before is not None:
            scan.warnings.append(
                f"@{creator_id} 的歷史回補狀態同時標記完成與 cursor={cursor_before}；"
                "本次依 cursor 安全重掃。"
            )
        try:
            page_index = int(cursor_before) if cursor_before is not None else 1
        except ValueError:
            page_index = 1
            scan.warnings.append(f"@{creator_id} 的歷史回補 cursor 無效；本次從第 2 頁安全重掃。")
        if page_index < 1:
            page_index = 1
            scan.warnings.append(f"@{creator_id} 的歷史回補 cursor 小於 1；本次從第 2 頁安全重掃。")
        if page_index >= len(pages):
            scan.backfill_completed = True
            scan.stop_reason = "remote_exhausted"
            return scan

        scan.backfill_page = page_index
        while page_index < len(pages) and len(scan.items) < max_posts:
            actionable: list[str] = []
            threshold_hit = False
            scan.pages_scanned += 1
            for summary in self.client.creator_page(pages[page_index]):
                if summary.post_id in seen:
                    continue
                seen.add(summary.post_id)
                scan.discovered += 1
                item = self._classify(creator_id, summary, "backfill")
                if item is None:
                    scan.skipped += 1
                    recent_unchanged += 1
                    if recent_unchanged >= self.archive.config.sync.recent_unchanged_stop_count:
                        threshold_hit = True
                        break
                else:
                    recent_unchanged = 0
                    scan.items.append(item)
                    actionable.append(summary.post_id)
            next_page = page_index if threshold_hit else page_index + 1
            exhausted = next_page >= len(pages)
            scan.backfill_batches.append(BackfillBatch(
                page_index=page_index, next_page=next_page,
                actionable_post_ids=actionable, remote_exhausted=exhausted,
            ))
            scan.next_backfill_page = next_page
            if threshold_hit:
                scan.stop_reason = "unchanged_threshold"
                break
            page_index = next_page

        if scan.stop_reason == "unchanged_threshold":
            return scan
        scan.backfill_completed = page_index >= len(pages)
        scan.stop_reason = "remote_exhausted" if scan.backfill_completed else "limit_reached"
        return scan

    def _classify(self, creator_id: str, summary: PostSummary, source: str) -> SyncItem | None:
        if summary.is_restricted:
            return None
        row = self.db.post_row(summary.post_id)
        if row is None:
            return SyncItem(creator_id, summary, "new", source)  # type: ignore[arg-type]
        if self.mutate and bool(row["is_pinned"]) != summary.is_pinned:
            self.db.set_post_pinned(summary.post_id, summary.is_pinned)
        if row["status"] != PostStatus.COMPLETED.value:
            return SyncItem(creator_id, summary, "retry", source)  # type: ignore[arg-type]
        if summary.updated_at and row["updated_at"] and _same_instant(summary.updated_at, row["updated_at"]):
            return None
        return SyncItem(creator_id, summary, "updated", source)  # type: ignore[arg-type]

    @staticmethod
    def _round_robin_all(scans: list[CreatorScan]):
        queues = [deque(scan.items) for scan in scans]
        while any(queues):
            for queue in queues:
                if queue:
                    yield queue.popleft()


def _same_instant(left: str, right: str) -> bool:
    try:
        return datetime.fromisoformat(left.replace("Z", "+00:00")) == datetime.fromisoformat(right.replace("Z", "+00:00"))
    except ValueError:
        return left == right
