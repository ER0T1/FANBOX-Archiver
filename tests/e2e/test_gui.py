from __future__ import annotations

import os
import socket
import threading
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import uvicorn
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, expect, sync_playwright

from fanbox_archiver.config import AppConfig, StorageConfig
from fanbox_archiver.indexer import IndexBuilder
from fanbox_archiver.models import ContentBlock, CreatorProfile, CreatorProfileItem, Post
from fanbox_archiver.service import ArchiveService
from fanbox_archiver.webapp import create_app


pytestmark = pytest.mark.e2e


class PollingJobFixture:
    """Controllable running-to-completed job used to exercise browser polling."""

    def __init__(self) -> None:
        self.config: AppConfig | None = None
        self.verify_get_calls = 0
        self.verify_submitted = False
        self.hold_backup = True
        self.submitted: list = []

    def _snapshot(self, *, include_events: bool = True) -> dict:
        completed = not self.hold_backup
        events = [
            {
                "kind": "plan_ready",
                "timestamp": "2026-10-29T00:00:01+00:00",
                "data": {
                    "new": 2,
                    "updated": 0,
                    "retried": 0,
                    "skipped": 53,
                    "discovered": 55,
                    "eligible": 2,
                    "selected": 2,
                    "deferred": 0,
                    "requested_max_posts": 20,
                    "pages_scanned": 2,
                    "available_pages": 32,
                    "stop_reason": "eligible_exhausted",
                    "creators": ["alice"],
                    "scans": [{
                        "creator_id": "alice", "new": 2, "updated": 0,
                        "retry": 0, "skipped": 53, "discovered": 55,
                        "profile": "unchanged",
                    }],
                },
            },
            {
                "kind": "asset_progress",
                "timestamp": "2026-10-29T00:00:02+00:00",
                "data": {"asset_id": "cover", "name": "cover.jpg", "downloaded": 512, "total": 1024},
            },
        ]
        if completed:
            events.append({
                "kind": "job_finished",
                "timestamp": "2026-10-29T00:00:03+00:00",
                "data": {"success": 2, "failure": 0, "dry_run": False},
            })
        value = {
            "job_id": "e2e-job",
            "kind": "backup",
            "status": "completed" if completed else "running",
            "created_at": "2026-10-29T00:00:00+00:00",
            "started_at": "2026-10-29T00:00:00+00:00",
            "finished_at": "2026-10-29T00:00:03+00:00" if completed else None,
            "updated_at": "2026-10-29T00:00:03+00:00" if completed else "2026-10-29T00:00:02+00:00",
            "error": None,
            "request": {"creator": None, "dry_run": False, "max_posts": 20, "mode": "full"},
            "result": ({"selected": 2, "success": 2, "failure": 0, "unchanged": 0} if completed else None),
            "event_count": len(events),
        }
        if include_events:
            value["events"] = events
        return value

    def list(self) -> list[dict]:
        items = [self._snapshot(include_events=False)]
        if self.submitted:
            items.insert(0, self._submitted_snapshot(include_events=False))
        if self.verify_submitted:
            items.insert(0, self._verify_snapshot(include_events=False))
        return items

    def get(self, job_id: str) -> dict | None:
        if job_id == "e2e-verify":
            self.verify_get_calls += 1
            return self._verify_snapshot()
        if job_id != "e2e-job":
            return self._submitted_snapshot() if job_id == "submitted-job" and self.submitted else None
        return self._snapshot()

    def submit(self, request) -> dict:
        self.submitted.append(request)
        return self._submitted_snapshot()

    def _submitted_snapshot(self, *, include_events: bool = True) -> dict:
        request = asdict(self.submitted[-1])
        value = {
            "job_id": "submitted-job", "kind": "backup", "status": "completed",
            "created_at": "2026-10-30T00:00:00+00:00", "started_at": None,
            "finished_at": "2026-10-30T00:00:01+00:00", "updated_at": "2026-10-30T00:00:01+00:00",
            "error": None, "request": request,
            "result": {"selected": 0, "success": 0, "failure": 0, "unchanged": 0},
            "event_count": 0,
        }
        if include_events:
            value["events"] = []
        return value

    def has_active(self) -> bool:
        return self.hold_backup or (self.verify_submitted and self.verify_get_calls < 1)

    def submit_verify(self) -> dict:
        self.verify_submitted = True
        return self._verify_snapshot()

    def _verify_snapshot(self, *, include_events: bool = True) -> dict:
        completed = self.verify_get_calls >= 1
        value = {
            "job_id": "e2e-verify",
            "kind": "verify",
            "status": "completed" if completed else "running",
            "created_at": "2026-10-29T00:01:00+00:00",
            "started_at": "2026-10-29T00:01:00+00:00",
            "finished_at": "2026-10-29T00:01:01+00:00" if completed else None,
            "updated_at": "2026-10-29T00:01:01+00:00",
            "error": None,
            "request": {},
            "result": ({"passed": True, "issue_count": 0, "issues": [], "truncated": False}
                       if completed else None),
            "event_count": 2 if completed else 1,
        }
        if include_events:
            value["events"] = [{
                "kind": "verify_started", "timestamp": "2026-10-29T00:01:00+00:00", "data": {},
            }]
            if completed:
                value["events"].append({
                    "kind": "verify_finished", "timestamp": "2026-10-29T00:01:01+00:00",
                    "data": {"issue_count": 0, "shown": 0},
                })
        return value

    def close(self) -> None:
        return None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _archive_fixture(tmp_path: Path) -> tuple[AppConfig, Path]:
    config = AppConfig(storage=StorageConfig(
        output_dir=tmp_path / "FANBOX",
        database=tmp_path / "FANBOX" / "backup.db",
    ))
    archive = ArchiveService(config)
    archive.db.record_supporting_creators([("bob", "Bob")])
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for number in range(55):
        title = f"投稿 {number:02d}"
        if number == 27:
            title += " 稀有關鍵字"
        post = Post(
            post_id=str(1000 + number),
            creator_id="alice",
            creator_name="Alice",
            title=title,
            published_at=start + timedelta(days=number),
            updated_at=start + timedelta(days=number),
            url=f"https://www.fanbox.cc/@alice/posts/{1000 + number}",
            fee_required=300 if number % 2 else 0,
            blocks=[ContentBlock(type="paragraph", text=f"第 {number:02d} 篇正文")],
            raw={"isPinned": number == 0},
            content_fingerprint=f"e2e-{number}",
        )
        archive.save(post, download_assets=False)
    profile = CreatorProfile(
        creator_id="alice", name="Alice", description="離線保存的創作者介紹",
        profile_items=[CreatorProfileItem(
            type="website", label="作品集", url="https://example.test", description="公開連結",
        )],
        is_accepting_request=True, fanbox_url="https://www.fanbox.cc/@alice",
    )
    profile.content_fingerprint = profile.calculate_fingerprint()
    archive.save_profile(profile)
    archive.save_fancard({"body": {
        "plan": {
            "id": "gold", "title": "Gold", "fee": 1000,
            "description": "Fan Card 密碼：example", "creatorId": "alice",
            "user": {"name": "Alice"}, "perks": [
                {"name": "discord", "available": True, "supporterAccessible": True},
                {"name": "future-benefit"},
            ],
        },
        "supportStartDatetime": "2026-10-01T00:00:00+09:00",
        "supportTransactions": [{"targetMonth": "2026-10"}],
        "supporterCardImageUrl": None,
    }}, None, None)
    return config, tmp_path / "config.yaml"


def test_static_archive_stays_offline_at_desktop_and_narrow_width(page: Page, tmp_path: Path):
    config, _ = _archive_fixture(tmp_path)
    IndexBuilder(config).build()
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))
    index_url = (config.storage.output_dir / "index.html").as_uri()

    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{index_url}#view=creators")
    expect(page.locator("h1", has_text="創作者")).to_be_visible()
    expect(page.get_by_role("link", name="Creator Profile")).to_be_visible()
    page.get_by_role("link", name="Creator Profile").click()
    expect(page.get_by_role("heading", name="Alice", exact=True)).to_be_visible()
    expect(page.get_by_text("離線保存的創作者介紹")).to_be_visible()

    static_card_url = (
        config.storage.output_dir / "_site/fancards/alice/2026-10/latest.html"
    ).as_uri()
    page.goto(static_card_url)
    expect(page.get_by_role("heading", name="方案權益", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="加入 Discord 伺服器", exact=True)).to_be_visible()
    expect(page.get_by_text("目前可使用", exact=True)).to_be_visible()
    expect(page.get_by_text("Discord 連結可在帳號設定中編輯。", exact=False)).to_be_visible()
    expect(page.get_by_role("link", name="在 FANBOX 開啟 Discord", exact=False)).to_have_attribute(
        "href", "https://www.fanbox.cc/@alice/plans",
    )

    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(static_card_url)
    expect(page.get_by_role("heading", name="方案權益", exact=True)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert not any(url.startswith(("http://", "https://")) for url in requests)


@pytest.fixture
def live_gui(tmp_path: Path):
    config, config_path = _archive_fixture(tmp_path)
    app = create_app(config, config_path=config_path)
    app.state.jobs.close()
    jobs = PollingJobFixture()
    jobs.config = config
    app.state.jobs = jobs
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", access_log=False,
    ))
    thread = threading.Thread(target=server.run, name="fanbox-e2e-server", daemon=True)
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
        pytest.fail("GUI E2E server did not start")
    try:
        yield base_url, config_path, jobs
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        jobs.close()


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        browser_name = os.environ.get("FANBOX_E2E_BROWSER", "chrome")
        try:
            browser = (playwright.chromium.launch(headless=True) if browser_name == "chromium"
                       else playwright.chromium.launch(channel=browser_name, headless=True))
        except PlaywrightError as exc:
            message = f"GUI E2E requires the Playwright {browser_name} browser: {exc}"
            if os.environ.get("CI"):
                pytest.fail(message)
            pytest.skip(message)
        context = browser.new_context(locale="zh-TW", timezone_id="Asia/Taipei")
        current_page = context.new_page()
        try:
            yield current_page
        finally:
            context.close()
            browser.close()


def test_gui_navigation_search_pagination_settings_and_job_polling(
    page: Page, live_gui,
) -> None:
    base_url, config_path, jobs = live_gui
    page.goto(base_url, wait_until="networkidle")

    expect(page.get_by_role("heading", name="投稿", exact=True)).to_be_visible()
    expect(page.get_by_text("55 篇備份", exact=True)).to_be_visible()
    expect(page.locator('summary[aria-label="目前第 1 頁，共 2 頁"]')).to_be_visible()

    page.get_by_role("button", name="下一頁 →").click()
    expect(page.locator('summary[aria-label="目前第 2 頁，共 2 頁"]')).to_be_visible()
    expect(page.get_by_text("投稿 00", exact=True)).to_be_visible()

    search = page.get_by_role("searchbox", name="搜尋文章")
    search.fill("稀有關鍵字")
    expect(page.get_by_text("1 篇備份", exact=True)).to_be_visible()
    expect(page.get_by_text("投稿 27 稀有關鍵字", exact=True)).to_be_visible()
    search.fill("")
    expect(page.get_by_text("55 篇備份", exact=True)).to_be_visible()

    page.get_by_text("投稿 54", exact=True).click()
    expect(page.get_by_role("heading", name="投稿 54", exact=True)).to_be_visible()
    expect(page.get_by_text("1 / 55", exact=True).first).to_be_visible()
    page.keyboard.press("ArrowRight")
    expect(page.get_by_role("heading", name="投稿 53", exact=True)).to_be_visible()

    page.get_by_role("button", name="備份", exact=True).click()
    expect(page.get_by_role("heading", name="備份工作", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="本次備份摘要", exact=True)).to_be_visible()
    expect(page.locator(".plan-capacity")).to_contain_text("上限 20／發現 55／符合 2／選取 2／略過 53")
    expect(page.get_by_text("其餘投稿不需下載", exact=True)).to_be_visible()
    expect(page.get_by_text("cover.jpg", exact=True)).to_be_visible()

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    scroll_y = page.evaluate("window.scrollY")
    assert scroll_y > 0
    page.wait_for_timeout(1_200)
    assert page.evaluate("window.scrollY") == scroll_y
    expect(page.get_by_text("正在讀取工作狀態…", exact=True)).not_to_be_visible()

    page.get_by_role("button", name="維護", exact=True).click()
    expect(page.get_by_text("目前工作：完整備份", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="目前無法驗證", exact=True)).to_be_disabled()

    page.get_by_role("button", name="設定", exact=True).click()
    expect(page.get_by_role("heading", name="設定", exact=True)).to_be_visible()
    expect(page.get_by_text("目前工作：完整備份", exact=True)).to_be_visible()
    save_button = page.get_by_role("button", name="儲存設定", exact=True)
    expect(save_button).to_be_disabled()
    jobs.hold_backup = False
    expect(save_button).to_be_enabled(timeout=5_000)
    expect(page.get_by_text("目前工作：完整備份", exact=True)).not_to_be_visible()
    expect(page.get_by_role("heading", name="備份", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="輸出與紀錄", exact=True)).to_be_visible()
    expect(page.get_by_text("DOWNLOAD", exact=True)).not_to_be_visible()
    expect(page.get_by_text("SYNC", exact=True)).not_to_be_visible()
    expect(page.get_by_text("BACKUP DEFAULTS", exact=True)).not_to_be_visible()
    max_posts = page.get_by_role("spinbutton", name="單次最多下載投稿數")
    max_posts.fill("25")
    unchanged_stop = page.get_by_role("spinbutton", name="連續未變投稿停止掃描數")
    unchanged_stop.fill("50")
    page.get_by_role("checkbox", name="完整備份只預覽，不下載").check()
    page.get_by_role("checkbox", name="預設拉取個人資料").uncheck()
    page.route("**/api/config", lambda route: route.fulfill(
        status=422, content_type="application/json", body='{"detail":"模擬儲存失敗"}',
    ), times=1)
    save_button.click()
    expect(page.get_by_text("儲存失敗：模擬儲存失敗", exact=True)).to_be_visible()
    expect(max_posts).to_have_value("25")
    save_button.click()
    expect(page.get_by_text("設定已安全寫入", exact=False)).to_be_visible()
    assert AppConfig.load(config_path).sync.max_posts_per_run == 25
    assert AppConfig.load(config_path).sync.recent_unchanged_stop_count == 50
    assert AppConfig.load(config_path).backup_defaults.dry_run is True
    assert AppConfig.load(config_path).backup_defaults.include_profile is False

    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.set_viewport_size({"width": 1280, "height": 800})

    page.get_by_role("button", name="備份", exact=True).click()
    expect(page.get_by_role("heading", name="開始備份", exact=True)).to_be_visible()
    expect(page.get_by_role("spinbutton", name="本次投稿上限")).to_have_value("25")
    expect(page.get_by_role("checkbox", name="完整備份只預覽，不下載")).to_be_checked()
    expect(page.get_by_role("checkbox", name="拉取個人資料", exact=True)).not_to_be_checked()
    expect(page.get_by_role("checkbox", name="拉取粉絲卡", exact=True)).to_be_checked()
    expect(page.get_by_text("尚未指定創作者；將備份全部支援中的創作者", exact=True)).to_be_visible()
    history_button = page.get_by_role("button", name="工作歷史", exact=True)
    expect(history_button).to_have_class("primary")
    creator_search = page.get_by_role("combobox", name="搜尋並加入創作者")
    creator_menu = page.locator(".creator-combobox-menu")
    creator_search.click()
    expect(creator_menu).to_be_visible()
    page.get_by_role("heading", name="開始備份", exact=True).click()
    expect(creator_menu).to_be_hidden()
    expect(creator_search).to_have_attribute("aria-expanded", "false")
    creator_search.click()
    expect(creator_menu).to_be_visible()
    history_button.click()
    expect(page.get_by_role("heading", name="工作歷史", exact=True)).to_be_visible()
    page.get_by_role("button", name="建立新工作", exact=True).click()
    creator_search = page.get_by_role("combobox", name="搜尋並加入創作者")
    creator_search.fill("ali")
    page.keyboard.press("Enter")
    creator_search.fill("BOB")
    page.keyboard.press("Enter")
    expect(page.get_by_text("已選 2 位", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="移除 Alice @alice")).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.set_viewport_size({"width": 1280, "height": 800})
    page.get_by_role("button", name="開始完整備份", exact=True).click()
    expect(page.get_by_role("heading", name="2 位創作者", exact=True)).to_be_visible()
    assert jobs.submitted[-1].creators == ("alice", "bob")
    assert jobs.submitted[-1].dry_run is True
    assert jobs.submitted[-1].max_posts == 25
    assert jobs.submitted[-1].include_profile is False
    assert jobs.submitted[-1].include_fancard is True

    page.get_by_role("button", name="創作者", exact=True).click()
    page.locator(".creator-card").filter(has_text="Alice").click()
    expect(page.get_by_role("heading", name="關於創作者", exact=True)).to_be_visible()
    expect(page.get_by_text("離線保存的創作者介紹", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="作品集", exact=False)).to_be_visible()
    page.locator('[data-creator-tab="posts"]').click()
    first_creator_post = page.locator(".creator-posts .post-card").first
    expect(first_creator_post).to_contain_text("投稿 00")
    expect(first_creator_post).to_contain_text("置頂")

    page.locator('[data-creator-tab="fancards"]').click()
    expect(page.get_by_text("Gold", exact=True)).to_be_visible()
    page.locator(".fancard-card").click()
    expect(page.get_by_role("heading", name="方案資訊", exact=True)).to_be_visible()
    expect(page.get_by_text("Fan Card 密碼：example", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="方案權益", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="加入 Discord 伺服器", exact=True)).to_be_visible()
    expect(page.get_by_text("目前可使用", exact=True)).to_be_visible()
    expect(page.get_by_text("Discord 連結可在帳號設定中編輯。", exact=False)).to_be_visible()
    expect(page.get_by_role("link", name="在 FANBOX 開啟 Discord", exact=False)).to_have_attribute(
        "href", "https://www.fanbox.cc/@alice/plans",
    )
    expect(page.get_by_text("狀態未知", exact=True)).to_be_visible()
    expect(page.get_by_text("supporterAccessible", exact=False)).to_have_count(0)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.set_viewport_size({"width": 1280, "height": 800})

    page.get_by_role("button", name="維護", exact=True).click()
    expect(page.get_by_role("heading", name="封存驗證", exact=True)).to_be_visible()
    page.get_by_role("button", name="開始驗證", exact=True).click()
    expect(page.locator(".verification-summary strong")).to_have_text("驗證通過", timeout=5_000)
    assert jobs.verify_get_calls >= 1
