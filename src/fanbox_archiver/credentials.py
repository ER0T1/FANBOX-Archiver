from __future__ import annotations

from .i18n import Text

import os
from http.cookiejar import CookieJar


SUPPORTED_BROWSERS = {"chrome", "edge", "firefox", "brave", "chromium", "opera", "vivaldi"}


def cookie_header(
    browser: str | None = None,
    *,
    profile_dir: os.PathLike[str] | None = None,
    browser_channel: str = "chrome",
) -> str:
    """Return FANBOX cookies from the environment or an explicitly selected browser.

    The values remain in memory and are never persisted by FANBOX Archiver.
    """
    from_environment = os.environ.get("FANBOX_COOKIE", "").strip()
    if from_environment:
        _reject_header_injection(from_environment)
        return from_environment
    if browser:
        browser = browser.casefold()
        if browser not in SUPPORTED_BROWSERS:
            raise ValueError(Text("credentials.unsupported_browser", browser=browser))

        import browser_cookie3

        loader = getattr(browser_cookie3, browser)
        try:
            jar: CookieJar = loader(domain_name="fanbox.cc")
        except Exception as exc:
            raise RuntimeError(Text("credentials.read_failed", browser=browser)) from exc
        values: list[str] = []
        for item in jar:
            domain = item.domain.lstrip(".").casefold()
            if domain == "fanbox.cc" or domain.endswith(".fanbox.cc"):
                values.append(f"{item.name}={item.value}")
        header = "; ".join(values)
    elif profile_dir is not None:
        from pathlib import Path

        from .browser_session import profile_cookie_header

        header = profile_cookie_header(Path(profile_dir), channel=browser_channel)
    else:
        return ""
    _reject_header_injection(header)
    if not header:
        source = browser or Text("credentials.profile_source")
        raise RuntimeError(Text("credentials.cookie_missing", source=source))
    return header


def _reject_header_injection(value: str) -> None:
    if "\r" in value or "\n" in value:
        raise ValueError(Text("credentials.header_newline"))
