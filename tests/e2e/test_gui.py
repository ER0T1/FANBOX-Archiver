from __future__ import annotations

from contextlib import contextmanager

import os
import re
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
from fanbox_archiver.application import AuthStatus
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
        self.created_at = "2026-10-29T00:00:00+00:00"
        self.history: list[dict] = []

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
                "kind": "item_started",
                "timestamp": "2026-10-29T00:00:02+00:00",
                "data": {"index": 1, "total": 2, "post_id": "1000", "creator_id": "alice"},
            },
            {
                "kind": "asset_progress",
                "timestamp": "2026-10-29T00:00:02+00:00",
                "data": {"asset_id": "cover", "name": "cover.jpg", "downloaded": 512,
                         "total": 1024},
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
            "created_at": self.created_at,
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
        return items + self.history

    def page(self, *, kind=None, status=None, ascending=False, page=1, page_size=20) -> dict:
        everything = self.list()
        items = [item for item in everything
                 if (kind is None or item["kind"] == kind) and (status is None or item["status"] == status)]
        items.sort(key=lambda item: (item["created_at"], item["job_id"]), reverse=not ascending)
        pages = max(1, -(-len(items) // page_size))
        page = min(max(1, page), pages)
        active = next((item for item in everything if item["status"] in {"queued", "running", "cancelling"}), None)
        return {"items": items[(page - 1) * page_size:page * page_size], "page": page, "pages": pages,
                "page_size": page_size, "total": len(items), "active": active}

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
        return self.hold_backup or (self.verify_submitted and self.verify_get_calls < 2)

    def submit_verify(self) -> dict:
        self.verify_submitted = True
        return self._verify_snapshot()

    def _verify_snapshot(self, *, include_events: bool = True) -> dict:
        completed = self.verify_get_calls >= 2
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
            "event_count": 3 if completed else 2,
        }
        if include_events:
            value["events"] = [{
                "kind": "verify_started", "timestamp": "2026-10-29T00:01:00+00:00", "data": {},
            }, {
                "kind": "verify_progress", "timestamp": "2026-10-29T00:01:00+00:00",
                "data": ({"phase": "scan", "current": 0, "total": None, "percent": None,
                          "item": "掃描封存驗證項目", "issue_count": 0}
                         if self.verify_get_calls == 0 else
                         {"phase": "posts", "current": 3, "total": 8, "percent": 37.5,
                          "item": "Post 1000 資源 cover", "issue_count": 0}),
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
            tags=[
                "共同",
                *(["奇數"] if number % 2 else []),
                *(["精選"] if number % 10 == 0 else []),
            ],
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
    }}, None, None, captured_at="2026-10-15T03:00:00+00:00")
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
    _expect_github_link(page, label_visible=True)
    page.locator(".creator-card").filter(has_text="Alice").get_by_role("button", name="查看文章 →").click()
    expect(page.get_by_role("button", name="全部 55", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="奇數 27", exact=True)).to_be_visible()
    page.get_by_role("button", name="奇數 27", exact=True).click()
    expect(page.locator(".page-heading")).to_contain_text("27 筆符合目前條件")
    expect(page.locator(".post-card").first).to_contain_text("奇數")
    page.go_back()
    expect(page.get_by_role("button", name="全部 55", exact=True)).to_have_attribute("aria-pressed", "true")
    static_cards = page.locator(".post-card")
    expect(static_cards).to_have_count(20)
    expect(page.locator(".pagination")).to_contain_text("第 1 / 3 頁")
    expect(static_cards.first).to_contain_text("投稿 00")  # pinned
    expect(static_cards.nth(1)).to_contain_text("投稿 54")
    page.get_by_role("button", name="時間排序：新到舊，按下切換").click()
    expect(static_cards.first).to_contain_text("投稿 00")
    expect(static_cards.nth(1)).to_contain_text("投稿 01")
    assert "order=asc" in page.url
    page.get_by_role("combobox", name="排序方式").select_option("title")
    expect(page.get_by_role("button", name="時間排序只適用於發布或更新時間")).to_be_disabled()
    page.goto(f"{index_url}#view=posts&sort=published-desc")
    expect(static_cards.first).to_contain_text("投稿 54")
    page.goto(f"{index_url}#view=creators")
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

    _expect_github_link(page, label_visible=True)

    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(static_card_url)
    expect(page.get_by_role("heading", name="方案權益", exact=True)).to_be_visible()
    _expect_github_link(page, label_visible=False)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.goto(f"{index_url}#view=posts")
    _expect_github_link(page, label_visible=False)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert not any(url.startswith(("http://", "https://")) for url in requests)


def _expect_github_link(page: Page, *, label_visible: bool) -> None:
    """The repository link is click-only: exact URL, new tab, no opener, and an accessible name."""
    link = page.get_by_role("link", name="GitHub 倉庫（另開新分頁）")
    expect(link).to_have_count(1)
    expect(link).to_be_visible()
    expect(link).to_have_attribute("href", "https://github.com/ER0T1/FANBOX-Archiver")
    expect(link).to_have_attribute("target", "_blank")
    expect(link).to_have_attribute("rel", "noopener noreferrer")
    label = link.locator(".github-label")
    expect(label).to_be_visible() if label_visible else expect(label).to_be_hidden()
    link.focus()
    expect(link).to_be_focused()


@pytest.fixture
def live_gui(tmp_path: Path):
    config, config_path = _archive_fixture(tmp_path)
    app = create_app(config, config_path=config_path)
    class SignedOutAuth:
        def check(self):
            return AuthStatus("signed_out", "none", "尚未建立 FANBOX 登入工作階段。", True, False)

    app.state.auth_service = SignedOutAuth()
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


@contextmanager
def _browser_page(timezone_id: str):
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
        context = browser.new_context(locale="zh-TW", timezone_id=timezone_id)
        current_page = context.new_page()
        try:
            yield current_page
        finally:
            context.close()
            browser.close()


@pytest.fixture
def page():
    with _browser_page("Asia/Taipei") as current_page:
        yield current_page


@pytest.fixture
def tokyo_page():
    # A browser in another zone must still show the server's display timezone.
    with _browser_page("Asia/Tokyo") as current_page:
        yield current_page


def test_job_history_uses_the_display_timezone_not_the_browser_timezone(
    tokyo_page: Page, live_gui,
) -> None:
    base_url, config_path, jobs = live_gui
    jobs.created_at = "2026-11-02T16:00:00+00:00"  # 11-03 00:00 in Taipei, 11-03 01:00 in Tokyo
    jobs.hold_backup = False
    assert tokyo_page.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone") == "Asia/Tokyo"
    tokyo_page.goto(base_url, wait_until="networkidle")
    tokyo_page.get_by_role("button", name="備份", exact=True).click()
    tokyo_page.get_by_role("button", name="工作歷史", exact=True).click()
    expect(tokyo_page.get_by_role("heading", name="工作歷史", exact=True)).to_be_visible()
    history = tokyo_page.locator(".job-history")
    expect(history.get_by_text("2026年11月03日 00:00").first).to_be_visible()
    expect(history.get_by_text("2026年11月03日 01:00")).to_have_count(0)

    # Choosing Asia/Tokyo in settings moves every displayed time, in 24-hour form.
    tokyo_page.get_by_role("button", name="設定", exact=True).click()
    tokyo_page.get_by_role("combobox", name="時區", exact=True).click()
    tokyo_page.get_by_role("option", name="Asia/Tokyo", exact=True).click()
    tokyo_page.get_by_role("button", name="儲存設定", exact=True).click()
    expect(tokyo_page.get_by_text("設定已安全寫入", exact=False)).to_be_visible()
    assert AppConfig.load(config_path).display.timezone == "Asia/Tokyo"
    expect(tokyo_page.get_by_text("目前生效：Asia/Tokyo", exact=False)).to_be_visible()
    expect(tokyo_page.locator(".schedule-settings")).to_contain_text("Asia/Tokyo，24 小時制")
    body = tokyo_page.locator("body").inner_text()
    assert "上午" not in body and "下午" not in body
    tokyo_page.get_by_role("button", name="備份", exact=True).click()
    tokyo_page.get_by_role("button", name="工作歷史", exact=True).click()
    expect(history.get_by_text("2026年11月03日 01:00").first).to_be_visible()

    tokyo_page.get_by_role("button", name="設定", exact=True).click()
    tokyo_page.get_by_role("combobox", name="時區", exact=True).click()
    tokyo_page.get_by_role("option", name="其他時區…").click()
    other = tokyo_page.get_by_role("combobox", name="其他時區（IANA 名稱）")
    other.fill("Mars/Olympus")
    tokyo_page.get_by_role("button", name="儲存設定", exact=True).click()
    expect(tokyo_page.get_by_text("儲存失敗", exact=False)).to_be_visible()
    assert AppConfig.load(config_path).display.timezone == "Asia/Tokyo"


def test_gui_navigation_search_pagination_settings_and_job_polling(
    page: Page, live_gui,
) -> None:
    base_url, config_path, jobs = live_gui
    page.goto(base_url, wait_until="networkidle")

    expect(page.get_by_role("heading", name="投稿", exact=True)).to_be_visible()
    expect(page.get_by_text("55 篇備份", exact=True)).to_be_visible()
    expect(page.locator(".post-card").first).to_contain_text("共同")
    expect(page.locator('summary[aria-label="目前第 1 頁，共 3 頁"]')).to_be_visible()
    expect(page.locator(".post-card")).to_have_count(20)
    expect(page.locator(".post-card").first).to_contain_text("投稿 54")

    page.get_by_role("button", name="下一頁 →").click()
    expect(page.locator('summary[aria-label="目前第 2 頁，共 3 頁"]')).to_be_visible()
    page.get_by_role("button", name="下一頁 →").click()
    expect(page.locator('summary[aria-label="目前第 3 頁，共 3 頁"]')).to_be_visible()
    expect(page.get_by_text("投稿 00", exact=True)).to_be_visible()

    order = page.get_by_role("button", name="投稿時間排序：新到舊，按下切換")
    order.click()
    expect(page.locator('summary[aria-label="目前第 1 頁，共 3 頁"]')).to_be_visible()
    expect(page.locator(".post-card").first).to_contain_text("投稿 00")
    expect(page.get_by_role("button", name="投稿時間排序：舊到新，按下切換")).to_be_visible()
    page.get_by_role("button", name="投稿時間排序：舊到新，按下切換").click()
    expect(page.locator(".post-card").first).to_contain_text("投稿 54")

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
    expect(page.get_by_text("投稿 1 / 2", exact=True)).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.set_viewport_size({"width": 1280, "height": 800})

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
    expect(page.locator(".auth-badge")).to_have_text("工作中")
    expect(page.locator(".account-card")).not_to_have_class(re.compile(r"tone-error"))
    expect(page.get_by_text("檢查失敗", exact=True)).not_to_be_visible()
    for name in ("登入 FANBOX", "重新檢查", "登出"):
        expect(page.get_by_role("button", name=name, exact=True)).to_be_disabled()
    log_level = page.get_by_role("combobox", name="日誌等級")
    expect(log_level).to_have_attribute("aria-disabled", "true")
    log_level.click(force=True)
    log_level.press("ArrowDown")
    log_level.press("Enter")
    expect(page.locator("#log-level")).not_to_have_attribute("open", "")
    expect(page.get_by_role("option", name="DEBUG")).not_to_be_visible()
    jobs.hold_backup = False
    expect(save_button).to_be_enabled(timeout=5_000)
    expect(page.get_by_text("目前工作：完整備份", exact=True)).not_to_be_visible()
    expect(page.get_by_role("heading", name="帳號／登入", exact=True)).to_be_visible()
    expect(page.get_by_text("未登入", exact=True)).to_be_visible()
    log_level = page.get_by_role("combobox", name="日誌等級")
    expect(log_level).to_have_attribute("aria-disabled", "false")
    log_level.click()
    expect(page.get_by_role("option", name="DEBUG")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_role("button", name="登入 FANBOX", exact=True)).to_be_enabled()
    expect(page.get_by_role("button", name="登出", exact=True)).to_be_disabled()
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
    expect(page.get_by_text("備份前請確認登入", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="前往設定登入", exact=True)).to_be_visible()
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
    expect(first_creator_post).to_contain_text("共同")
    expect(page.get_by_role("button", name="全部 55", exact=True)).to_have_attribute("aria-pressed", "true")
    creator_cards = page.locator(".creator-posts .post-card")
    expect(creator_cards).to_have_count(20)
    expect(creator_cards.nth(1)).to_contain_text("投稿 54")
    page.get_by_role("button", name="投稿時間排序：新到舊，按下切換").click()
    expect(creator_cards.first).to_contain_text("投稿 00")  # pinned stays first in both orders
    expect(creator_cards.nth(1)).to_contain_text("投稿 01")
    page.get_by_role("button", name="投稿時間排序：舊到新，按下切換").click()
    expect(creator_cards.nth(1)).to_contain_text("投稿 54")
    expect(page.get_by_role("button", name="奇數 27", exact=True)).to_be_visible()
    page.get_by_role("button", name="奇數 27", exact=True).click()
    expect(creator_cards).to_have_count(20)
    expect(page.locator('.creator-posts summary[aria-label="目前第 1 頁，共 2 頁"]')).to_be_visible()
    expect(creator_cards.first).to_contain_text("奇數")
    page.get_by_role("button", name="下一頁 →").click()
    expect(creator_cards).to_have_count(7)
    search = page.get_by_role("searchbox", name="搜尋文章")
    search.fill("稀有關鍵字")
    expect(creator_cards).to_have_count(1)
    search.fill("")
    expect(creator_cards).to_have_count(20)
    page.go_back()
    expect(page.get_by_role("button", name="全部 55", exact=True)).to_have_attribute("aria-pressed", "true")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.set_viewport_size({"width": 1280, "height": 800})

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
    expect(page.get_by_text("正在建立固定驗證清單", exact=True)).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.set_viewport_size({"width": 1280, "height": 800})
    expect(page.get_by_role("heading", name="驗證投稿", exact=True)).to_be_visible(timeout=5_000)
    expect(page.locator(".verification-summary strong")).to_have_text("驗證通過", timeout=5_000)
    assert jobs.verify_get_calls >= 2


def test_job_history_pages_sorts_and_filters_on_the_server(page: Page, live_gui) -> None:
    base_url, _, jobs = live_gui
    jobs.hold_backup = False
    for index in range(25):
        created = f"2026-09-{1 + index:02d}T00:00:00+00:00"
        jobs.history.append({
            "job_id": f"old-{index:02d}", "kind": "backup",
            "status": "failed" if index % 5 == 0 else "completed",
            "created_at": created, "started_at": created, "finished_at": created, "updated_at": created,
            "error": None, "request": {"creators": [], "dry_run": False, "mode": "full"},
            "result": {"success": index, "failure": 0}, "event_count": 0,
        })
    page.goto(base_url, wait_until="networkidle")
    page.get_by_role("button", name="備份", exact=True).click()
    page.get_by_role("button", name="工作歷史", exact=True).click()
    rows = page.locator(".job-history .history-row")
    expect(rows).to_have_count(20)
    expect(page.locator('.job-history summary[aria-label="目前第 1 頁，共 2 頁"]')).to_be_visible()
    expect(rows.first).to_contain_text("2026年10月29日")
    page.get_by_role("button", name="下一頁 →").click()
    expect(rows).to_have_count(6)

    page.get_by_role("button", name="工作時間排序：新到舊，按下切換").click()
    expect(page.locator('.job-history summary[aria-label="目前第 1 頁，共 2 頁"]')).to_be_visible()
    expect(rows.first).to_contain_text("2026年09月01日")

    page.get_by_role("combobox", name="篩選工作狀態").click()
    page.get_by_role("option", name="失敗").click()
    expect(rows).to_have_count(5)
    expect(page.locator(".job-history .pagination")).to_have_count(0)
    expect(page.get_by_role("button", name="工作時間排序：舊到新，按下切換")).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_settings_auto_backup_previews_saves_and_runs_once(page: Page, live_gui) -> None:
    base_url, config_path, jobs = live_gui
    page.goto(base_url, wait_until="networkidle")
    page.get_by_role("button", name="設定", exact=True).click()
    section = page.locator(".schedule-settings")
    expect(section.get_by_role("heading", name="自動備份")).to_be_visible()
    # A running job locks the whole section, including the day grid and run button.
    expect(section.get_by_role("checkbox", name="啟用自動備份")).to_be_disabled()
    expect(section.get_by_role("button", name="立即執行一次")).to_be_disabled()
    jobs.hold_backup = False
    enable = section.get_by_role("checkbox", name="啟用自動備份")
    expect(enable).to_be_enabled(timeout=5_000)
    expect(section.locator("dd").first).to_have_text("未啟用")

    enable.check()
    section.get_by_role("combobox", name="週期").click()
    section.get_by_role("option", name="每週／每 N 週").click()
    section.get_by_role("combobox", name="星期").click()
    section.get_by_role("option", name="週三").click()
    section.get_by_role("spinbutton", name="間隔").fill("2")
    section.get_by_role("combobox", name="時", exact=True).click()
    section.get_by_role("option", name="21", exact=True).click()
    section.get_by_role("combobox", name="分", exact=True).click()
    section.get_by_role("option", name="05", exact=True).click()
    preview = section.locator(".schedule-preview")
    expect(preview).to_contain_text("每 2 週的週三 21:05（Asia/Taipei）")
    expect(preview).to_contain_text("接下來：")
    expect(section.locator(".schedule-days")).to_be_hidden()

    section.get_by_role("combobox", name="週期").click()
    section.get_by_role("option", name="每月指定日期").click()
    expect(section.get_by_role("spinbutton", name="間隔")).to_be_hidden()
    section.get_by_role("button", name="31", exact=True).click()
    expect(section.get_by_role("button", name="31", exact=True)).to_have_attribute("aria-pressed", "true")
    expect(preview).to_contain_text("每月 31 日 21:05")
    expect(preview).to_contain_text("月底執行")

    expect(section.locator(".schedule-background dd")).to_contain_text("只在 Windows 桌面版提供")
    section.get_by_role("combobox", name="電源與休眠").click()
    section.get_by_role("option", name="不喚醒電腦，只在接上電源時執行").click()
    page.get_by_role("button", name="儲存設定", exact=True).click()
    expect(page.get_by_text("設定已安全寫入", exact=False)).to_be_visible()
    saved = AppConfig.load(config_path).schedule
    assert saved.power == "no_wake_ac_only"
    assert (saved.enabled, saved.frequency, saved.month_day, saved.time) == (True, "monthly", 31, "21:05")
    assert saved.start_date is not None
    expect(section.locator("dd").first).to_contain_text("每月 31 日 21:05")
    expect(section.locator("dd").nth(1)).not_to_have_text("—")

    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.set_viewport_size({"width": 1280, "height": 800})
    section.get_by_role("button", name="立即執行一次").click()
    expect(page.get_by_role("heading", name="開始備份", exact=True)).to_be_visible()
    assert jobs.submitted[-1].trigger == "schedule"
    assert jobs.submitted[-1].dry_run is False



def test_background_scheduled_backup_locks_the_app_without_a_stop_button(page: Page, live_gui) -> None:
    base_url, _, jobs = live_gui
    jobs.hold_backup = False
    jobs.history.append({
        "job_id": "background-job", "kind": "backup", "status": "running", "external": True,
        "created_at": "2026-11-03T00:00:00+00:00", "started_at": "2026-11-03T00:00:00+00:00",
        "finished_at": None, "updated_at": "2026-11-03T00:00:00+00:00", "error": None,
        "request": {"creators": [], "dry_run": False, "mode": "full", "trigger": "schedule"},
        "result": None, "event_count": 0,
    })
    original_get = jobs.get
    jobs.get = lambda job_id: ({**jobs.history[0], "events": []} if job_id == "background-job" else original_get(job_id))
    page.goto(base_url, wait_until="networkidle")
    page.get_by_role("button", name="備份", exact=True).click()
    expect(page.get_by_role("heading", name="備份工作", exact=True)).to_be_visible()
    expect(page.get_by_text("排程備份", exact=True).first).to_be_visible()
    expect(page.get_by_text("此工作由背景排程在程式關閉期間開始", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="安全停止", exact=True)).to_have_count(0)
    page.get_by_role("button", name="設定", exact=True).click()
    expect(page.get_by_text("目前工作：排程備份", exact=True)).to_be_visible()
    expect(page.get_by_text("（背景執行中）", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="儲存設定", exact=True)).to_be_disabled()
    expect(page.get_by_role("checkbox", name="啟用自動備份")).to_be_disabled()


def test_settings_about_section_shows_versions_and_opens_fixed_folders(
    page: Page, live_gui, monkeypatch,
) -> None:
    import fanbox_archiver.diagnostics as diagnostics
    from fanbox_archiver import __version__

    opened: list[Path] = []
    monkeypatch.setattr(diagnostics, "open_folder", opened.append)
    monkeypatch.setattr(diagnostics, "can_open_folders", lambda: True)
    base_url, _config_path, _jobs = live_gui
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base_url)
    page.goto(base_url, wait_until="networkidle")
    page.get_by_role("button", name="設定", exact=True).click()

    about = page.locator(".about-card")
    expect(about.get_by_role("heading", name="關於與診斷")).to_be_visible()
    expect(about).to_contain_text(__version__)
    expect(about).to_contain_text("瀏覽器版")
    expect(about.get_by_role("button", name="開啟桌面日誌資料夾")).to_have_count(0)

    about.get_by_role("button", name="開啟封存資料夾").click()
    expect(about.get_by_role("status")).to_contain_text("已開啟")
    assert len(opened) == 1 and opened[0].name

    about.get_by_role("button", name="複製診斷資訊").click()
    expect(about.get_by_role("status")).to_contain_text("診斷資訊已複製")
    copied = page.evaluate("navigator.clipboard.readText()")
    assert f"程式版本：{__version__}" in copied
    assert "token" not in copied.casefold() and "cookie" not in copied.casefold()


def test_dynamic_topbar_github_link_is_keyboard_reachable_offline_and_responsive(
    page: Page, live_gui,
) -> None:
    base_url, _config_path, _jobs = live_gui
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))
    for width, label_visible in ((1280, True), (900, True), (390, False)):
        page.set_viewport_size({"width": width, "height": 844})
        page.goto(base_url, wait_until="networkidle")
        _expect_github_link(page, label_visible=label_visible)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), width

    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(base_url, wait_until="networkidle")
    page.locator("#search").focus()
    page.keyboard.press("Tab")
    link = page.get_by_role("link", name="GitHub 倉庫（另開新分頁）")
    expect(link).to_be_focused()
    assert link.evaluate("element => getComputedStyle(element).outlineStyle") != "none"
    assert all(url.startswith(base_url) for url in requests), [
        url for url in requests if not url.startswith(base_url)
    ]
