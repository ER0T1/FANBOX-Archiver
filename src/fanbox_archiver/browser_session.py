from __future__ import annotations

from .i18n import Text

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from playwright.sync_api import BrowserContext, Error as PlaywrightError, sync_playwright

from .security import validate_url


FANBOX_ORIGINS = [
    "https://www.fanbox.cc",
    "https://api.fanbox.cc",
    "https://downloads.fanbox.cc",
]
FANBOX_APP_URL = "https://www.fanbox.cc/"


class BrowserLoginError(RuntimeError):
    pass


class BrowserLoginCancelled(BrowserLoginError):
    pass


@dataclass(frozen=True, slots=True)
class BrowserAuthMaterial:
    cookie_header: str
    user_agent: str


class BrowserPostSession:
    """Reuse one authenticated background browser for post.info requests."""

    def __init__(self, profile_dir: Path, *, channel: str = "chrome", request_interval: float = 3.0):
        self.profile_dir = profile_dir
        self.channel = channel
        self.request_interval = max(0.0, request_interval)
        self._last_request = 0.0
        self._playwright = None
        self._context = None
        self._page = None

    def __enter__(self) -> "BrowserPostSession":
        if not self.profile_dir.exists():
            raise BrowserLoginError(Text("session.profile_missing"))
        try:
            self._playwright = sync_playwright().start()
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir), channel=self.channel, headless=True
            )
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
            self._page.goto(FANBOX_APP_URL, wait_until="domcontentloaded", timeout=60_000)
            self._last_request = time.monotonic()
            return self
        except PlaywrightError as exc:
            self.__exit__()
            raise BrowserLoginError(Text("session.start_failed", error=str(exc))) from exc

    def __exit__(self, *_: object) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except PlaywrightError:
                # Ctrl+C or a crashed browser may close the transport first.
                # Cleanup must not mask the original interruption/error.
                pass
            finally:
                self._context = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except PlaywrightError:
                pass
            finally:
                self._playwright = None

    def fetch(self, post_id: str) -> dict[str, Any]:
        if self._page is None:
            raise BrowserLoginError(Text("session.not_started"))
        remaining = self.request_interval - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)
        try:
            result = self._page.evaluate(
                """async (postId) => {
                  const controller = new AbortController();
                  const timer = setTimeout(() => controller.abort(), 60000);
                  try {
                    const response = await fetch(
                      `https://api.fanbox.cc/post.info?postId=${encodeURIComponent(postId)}`,
                      {credentials: "include", signal: controller.signal}
                    );
                    return {
                      status: response.status,
                      contentType: response.headers.get("content-type") || "",
                      text: await response.text()
                    };
                  } finally {
                    clearTimeout(timer);
                  }
                }""",
                post_id,
            )
            self._last_request = time.monotonic()
        except PlaywrightError as exc:
            raise BrowserLoginError(Text("session.post_request_failed", error=str(exc))) from exc
        return _decode_api_result(result)

    def fetch_fancard(self, creator_id: str) -> dict[str, Any]:
        url = f"https://api.fanbox.cc/legacy/support/creator?creatorId={quote(creator_id, safe='')}"
        return self._fetch_json(url)

    def fetch_binary(self, url: str) -> tuple[bytes, str]:
        validate_url(url, download=True)
        self._wait()
        try:
            response = self._page.request.get(url, timeout=60_000)
            self._last_request = time.monotonic()
        except PlaywrightError as exc:
            raise BrowserLoginError(Text("session.asset_request_failed", error=str(exc))) from exc
        if response.status != 200:
            raise BrowserLoginError(Text("session.fancard_image_http", status=str(response.status)))
        return response.body(), str(response.headers.get("content-type") or "application/octet-stream")

    def _fetch_json(self, url: str) -> dict[str, Any]:
        validate_url(url)
        self._wait()
        try:
            result = self._page.evaluate(
                """async (url) => {
                  const controller = new AbortController();
                  const timer = setTimeout(() => controller.abort(), 60000);
                  try {
                    const response = await fetch(url, {
                      credentials: "include", signal: controller.signal
                    });
                    return {status: response.status, text: await response.text()};
                  } finally {
                    clearTimeout(timer);
                  }
                }""",
                url,
            )
            self._last_request = time.monotonic()
        except PlaywrightError as exc:
            raise BrowserLoginError(Text("session.api_request_failed", error=str(exc))) from exc
        return _decode_api_result(result)

    def _wait(self) -> None:
        remaining = self.request_interval - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)


def _decode_api_result(result: dict[str, Any]) -> dict[str, Any]:
    from .client import (
        AccessRestrictedError, AuthenticationError, RateLimitedError, RemoteUnavailableError,
    )

    status = int(result.get("status") or 0)
    if status == 401:
        raise AuthenticationError(Text("session.auth_expired"))
    if status == 403:
        raise AccessRestrictedError(Text("client.access_restricted"))
    if status == 404:
        raise RemoteUnavailableError(Text("client.remote_unavailable"))
    if status == 429:
        raise RateLimitedError(Text("client.rate_limited"))
    if status != 200:
        raise BrowserLoginError(Text("session.page_request_http", status=str(status)))
    try:
        import json

        payload = json.loads(str(result.get("text") or ""))
    except (TypeError, ValueError) as exc:
        raise BrowserLoginError(Text("session.response_not_json")) from exc
    if not isinstance(payload, dict):
        raise BrowserLoginError(Text("session.response_invalid"))
    return payload


def interactive_login(
    profile_dir: Path,
    *,
    channel: str = "chrome",
    timeout_seconds: int = 600,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    """Open a dedicated browser profile and wait for the user to log in.

    Credentials are entered directly into FANBOX/pixiv by the user. This
    process observes only whether an authenticated FANBOX API request succeeds.
    """
    profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel=channel,
                headless=False,
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://www.fanbox.cc/", wait_until="domcontentloaded")
                _wait_for_authentication(context, timeout_seconds, should_cancel=should_cancel)
            finally:
                context.close()
    except BrowserLoginError:
        raise
    except PlaywrightError as exc:
        raise BrowserLoginError(Text("session.channel_start_failed", channel=channel, error=str(exc))) from exc


def profile_cookie_header(profile_dir: Path, *, channel: str = "chrome") -> str:
    return profile_auth_material(profile_dir, channel=channel).cookie_header


def profile_auth_material(profile_dir: Path, *, channel: str = "chrome") -> BrowserAuthMaterial:
    if not profile_dir.exists():
        return BrowserAuthMaterial("", "")
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel=channel,
                headless=True,
            )
            try:
                cookies = context.cookies(FANBOX_ORIGINS)
                page = context.pages[0] if context.pages else context.new_page()
                user_agent = str(page.evaluate("navigator.userAgent"))
            finally:
                context.close()
    except PlaywrightError as exc:
        raise BrowserLoginError(
            Text("session.profile_open_failed")
        ) from exc
    return BrowserAuthMaterial(cookies_to_header(cookies), user_agent)


def fetch_post_payload(
    profile_dir: Path,
    post_url: str,
    post_id: str,
    *,
    channel: str = "chrome",
) -> dict[str, Any]:
    """Fetch post.info inside a real FANBOX page with the saved browser session."""
    validate_url(post_url)
    if not profile_dir.exists():
        raise BrowserLoginError(Text("session.profile_missing"))
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel=channel,
                headless=True,
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                # A vanity post URL can redirect to creator-id.fanbox.cc.  FANBOX's
                # API CORS policy does not consistently allow those origins, so
                # execute the authenticated request from the canonical app origin.
                page.goto(FANBOX_APP_URL, wait_until="domcontentloaded", timeout=60_000)
                result = page.evaluate(
                    """async (postId) => {
                      const controller = new AbortController();
                      const timer = setTimeout(() => controller.abort(), 60000);
                      try {
                        const response = await fetch(
                          `https://api.fanbox.cc/post.info?postId=${encodeURIComponent(postId)}`,
                          {credentials: "include", signal: controller.signal}
                        );
                        return {
                          status: response.status,
                          contentType: response.headers.get("content-type") || "",
                          text: await response.text()
                        };
                      } finally {
                        clearTimeout(timer);
                      }
                    }""",
                    post_id,
                )
            finally:
                context.close()
    except PlaywrightError as exc:
        raise BrowserLoginError(Text("session.request_failed", error=str(exc))) from exc
    return _decode_api_result(result)


def profile_is_authenticated(profile_dir: Path, *, channel: str = "chrome") -> bool:
    if not profile_dir.exists():
        return False
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir), channel=channel, headless=True
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://www.fanbox.cc/", wait_until="domcontentloaded", timeout=60_000)
                result = page.evaluate(
                    """async () => {
                      const response = await fetch(
                        "https://api.fanbox.cc/plan.listSupporting",
                        { credentials: "include" }
                      );
                      return { status: response.status, text: await response.text() };
                    }"""
                )
            finally:
                context.close()
    except PlaywrightError as exc:
        raise BrowserLoginError(Text("session.verify_failed", error=str(exc))) from exc
    return int(result.get("status") or 0) == 200 and '"body"' in str(result.get("text") or "")


def clear_profile_authentication(profile_dir: Path, *, channel: str = "chrome") -> None:
    """Remove FANBOX authentication data without deleting the dedicated profile."""
    if not profile_dir.exists():
        return
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir), channel=channel, headless=True
            )
            try:
                context.clear_cookies(domain=re.compile(r"(^|\.)fanbox\.cc$"))
                page = context.pages[0] if context.pages else context.new_page()
                session = context.new_cdp_session(page)
                for origin in FANBOX_ORIGINS:
                    session.send(
                        "Storage.clearDataForOrigin",
                        {"origin": origin, "storageTypes": "local_storage"},
                    )
            finally:
                context.close()
    except PlaywrightError as exc:
        raise BrowserLoginError(
            Text("session.clear_failed")
        ) from exc


def cookies_to_header(cookies: list[dict[str, Any]]) -> str:
    values: list[str] = []
    for item in cookies:
        domain = str(item.get("domain") or "").lstrip(".").casefold()
        name = str(item.get("name") or "")
        value = str(item.get("value") or "")
        if name and (domain == "fanbox.cc" or domain.endswith(".fanbox.cc")):
            values.append(f"{name}={value}")
    return "; ".join(values)


def _wait_for_authentication(
    context: BrowserContext,
    timeout_seconds: int,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_status: int | None = None
    while time.monotonic() < deadline:
        if should_cancel is not None and should_cancel():
            raise BrowserLoginCancelled(Text("session.login_cancelled"))
        if not context.pages:
            raise BrowserLoginError(Text("session.login_window_closed"))
        try:
            page = context.pages[-1]
            if ".fanbox.cc" not in page.url and not page.url.startswith("https://www.fanbox.cc"):
                time.sleep(2)
                continue
            result = page.evaluate(
                """async () => {
                  const response = await fetch(
                    "https://api.fanbox.cc/plan.listSupporting",
                    { credentials: "include" }
                  );
                  return { status: response.status, text: await response.text() };
                }"""
            )
            last_status = int(result.get("status") or 0)
            if last_status == 200:
                import json

                payload = json.loads(str(result.get("text") or ""))
                if isinstance(payload, dict) and "body" in payload:
                    return
        except (PlaywrightError, TypeError, ValueError):
            pass
        for _ in range(20):
            if should_cancel is not None and should_cancel():
                raise BrowserLoginCancelled(Text("session.login_cancelled"))
            time.sleep(.1)
    raise BrowserLoginError(Text("session.login_timeout_status", status=str(last_status))
                            if last_status is not None else Text("session.login_timeout"))
