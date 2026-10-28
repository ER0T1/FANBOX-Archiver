from datetime import UTC, datetime
from pathlib import Path

from fanbox_archiver.client import (
    AccessRestrictedError, Creator, FanboxClient, PostSummary, RateLimitedError,
)
from fanbox_archiver.config import AppConfig, StorageConfig, SyncConfig
from fanbox_archiver.models import Post, PostStatus
from fanbox_archiver.service import ArchiveService
from fanbox_archiver.syncing import SyncCancelled, SyncService, SyncStopped


class FakeClient:
    def __init__(self, pages, posts=None):
        self.pages = pages
        self.posts = posts or {}

    def supporting_creators(self):
        return [Creator(creator_id, creator_id.upper()) for creator_id in self.pages]

    def creator_post_pages(self, creator_id):
        return [f"https://api.fanbox.cc/{creator_id}/{index}" for index in range(len(self.pages[creator_id]))]

    def creator_page(self, page_url):
        _, creator_id, index = page_url.rsplit("/", 2)
        return self.pages[creator_id][int(index)]

    def post(self, post_id):
        value = self.posts[post_id]
        if isinstance(value, Exception):
            raise value
        return value


def make_service(tmp_path: Path, pages, *, limit=20, posts=None):
    config = AppConfig(
        storage=StorageConfig(output_dir=tmp_path / "out", database=tmp_path / "out" / "db.sqlite"),
        sync=SyncConfig(max_posts_per_run=limit),
    )
    archive = ArchiveService(config)
    client = FakeClient(pages, posts)
    sync = SyncService(client, archive)  # type: ignore[arg-type]
    creators = sync.supporting_creators()
    return sync, archive, creators


def post(post_id: str, creator_id: str, fingerprint: str) -> Post:
    return Post(
        post_id=post_id, creator_id=creator_id, title=post_id,
        updated_at=datetime(2026, 1, int(post_id), tzinfo=UTC),
        url=f"https://www.fanbox.cc/@{creator_id}/posts/{post_id}",
        content_fingerprint=fingerprint,
    )


def test_creator_input_accepts_id_home_and_post_url():
    assert FanboxClient.creator_id("alice") == "alice"
    assert FanboxClient.creator_id("https://www.fanbox.cc/@alice") == "alice"
    assert FanboxClient.creator_id("https://www.fanbox.cc/@alice/posts/123") == "alice"


def test_post_id_accepts_creator_vanity_domain():
    assert FanboxClient.post_id_from_url(
        "https://tamatamo.fanbox.cc/posts/12435068"
    ) == "12435068"


def test_round_robin_plan_does_not_starve_later_creator(tmp_path: Path):
    pages = {
        "alice": [[PostSummary("1"), PostSummary("2")]],
        "bob": [[PostSummary("3"), PostSummary("4")]],
    }
    sync, _, creators = make_service(tmp_path, pages, limit=2)
    plan = sync.plan(creators, 2)
    assert [(item.creator_id, item.summary.post_id) for item in plan.selected] == [
        ("alice", "1"), ("bob", "3")
    ]


def test_completed_unchanged_post_does_not_use_limit(tmp_path: Path):
    pages = {"alice": [[
        PostSummary("1", "2026-01-01T00:00:00+00:00"),
        PostSummary("2", "2026-01-02T00:00:00+00:00"),
    ]]}
    posts = {"2": post("2", "alice", "new")}
    sync, archive, creators = make_service(tmp_path, pages, limit=1, posts=posts)
    old = post("1", "alice", "same")
    old.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    archive.db.upsert_post(old, str(tmp_path / "old"), PostStatus.COMPLETED)
    plan = sync.plan(creators, 1)
    assert plan.skipped == 1
    assert [item.summary.post_id for item in plan.selected] == ["2"]


def test_scan_updates_pin_metadata_without_redownloading_post(tmp_path: Path):
    pages = {"alice": [[
        PostSummary("1", "2026-01-01T00:00:00+00:00", is_pinned=True),
    ]]}
    sync, archive, creators = make_service(tmp_path, pages, limit=1)
    existing = post("1", "alice", "same")
    existing.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    archive.db.upsert_post(existing, str(tmp_path / "old"), PostStatus.COMPLETED)

    plan = sync.plan(creators, 1)

    assert plan.selected == []
    assert bool(archive.db.post_row("1")["is_pinned"]) is True


def test_backfill_cursor_advances_across_runs(tmp_path: Path):
    pages = {"alice": [
        [PostSummary("1", "2026-01-01T00:00:00+00:00")],
        [PostSummary("2", "2026-01-02T00:00:00+00:00")],
        [PostSummary("3", "2026-01-03T00:00:00+00:00")],
    ]}
    posts = {value: post(value, "alice", value) for value in ("1", "2", "3")}
    sync, archive, creators = make_service(tmp_path, pages, limit=2, posts=posts)
    first = sync.plan(creators, 2)
    sync.execute(first)
    state = archive.db.creator_state("alice")
    assert state["backfill_cursor"] == "2"
    second = sync.plan(creators, 2)
    assert any(item.summary.post_id == "3" for item in second.scans[0].items)


def test_creator_outside_supporting_list_is_rejected(tmp_path: Path):
    sync, _, _ = make_service(tmp_path, {"alice": [[]]})
    try:
        sync.resolve_creators("bob")
    except ValueError as exc:
        assert "不在目前支援清單" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_fatal_stop_preserves_results_completed_before_rate_limit(tmp_path: Path):
    pages = {"alice": [[PostSummary("1"), PostSummary("2")]]}
    posts = {"1": post("1", "alice", "one"), "2": RateLimitedError("429")}
    sync, _, creators = make_service(tmp_path, pages, limit=2, posts=posts)
    plan = sync.plan(creators, 2)
    try:
        sync.execute(plan)
    except SyncStopped as stopped:
        assert stopped.result.success == 1
        assert stopped.result.failure == 1
        assert isinstance(stopped.reason, RateLimitedError)
    else:
        raise AssertionError("expected SyncStopped")


def test_restricted_post_is_recorded_and_does_not_block_next_post(tmp_path: Path):
    pages = {"alice": [[PostSummary("1", title="restricted"), PostSummary("2")]]}
    posts = {"1": AccessRestrictedError("403"), "2": post("2", "alice", "two")}
    sync, archive, creators = make_service(tmp_path, pages, limit=2, posts=posts)
    result = sync.execute(sync.plan(creators, 2))
    assert result.failure == 1
    assert result.success == 1
    assert archive.db.post_row("1")["status"] == PostStatus.RESTRICTED.value
    assert archive.db.post_row("2")["status"] == PostStatus.COMPLETED.value


def test_summary_marked_restricted_is_skipped_without_fetching(tmp_path: Path):
    pages = {"alice": [[PostSummary("1", is_restricted=True), PostSummary("2")]]}
    sync, _, creators = make_service(tmp_path, pages, posts={"2": post("2", "alice", "two")})
    plan = sync.plan(creators, 20)
    assert plan.skipped == 1
    assert [item.summary.post_id for item in plan.selected] == ["2"]


def test_execute_can_cancel_safely_between_posts(tmp_path: Path):
    pages = {"alice": [[PostSummary("1")]]}
    sync, _, creators = make_service(
        tmp_path, pages, posts={"1": post("1", "alice", "one")}
    )
    plan = sync.plan(creators, 1)
    try:
        sync.execute(plan, should_cancel=lambda: True)
    except SyncCancelled as stopped:
        assert stopped.result.success == 0
        assert stopped.result.failure == 0
    else:
        raise AssertionError("expected SyncCancelled")
