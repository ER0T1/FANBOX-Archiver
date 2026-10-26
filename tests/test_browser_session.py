from playwright.sync_api import Error as PlaywrightError

from fanbox_archiver.browser_session import BrowserPostSession, fetch_post_payload


def test_browser_session_cleanup_ignores_already_closed_transport(tmp_path):
    class ClosedContext:
        def close(self):
            raise PlaywrightError("Connection closed while reading from the driver")

    class ClosedPlaywright:
        def stop(self):
            raise PlaywrightError("transport already closed")

    session = BrowserPostSession(tmp_path)
    session._context = ClosedContext()
    session._playwright = ClosedPlaywright()
    session.__exit__()
    assert session._context is None
    assert session._playwright is None


def test_single_post_fetch_uses_canonical_origin_for_vanity_url(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    profile.mkdir()

    class FakePage:
        def __init__(self):
            self.visited = []

        def goto(self, url, **_kwargs):
            self.visited.append(url)

        def evaluate(self, script, post_id):
            assert post_id == "12435068"
            assert "AbortController" in script
            return {"status": 200, "text": '{"body":{"id":"12435068"}}'}

    page = FakePage()

    class FakeContext:
        pages = [page]

        def close(self):
            pass

    class FakeChromium:
        def launch_persistent_context(self, **_kwargs):
            return FakeContext()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeManager:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, *_args):
            pass

    monkeypatch.setattr("fanbox_archiver.browser_session.sync_playwright", FakeManager)
    payload = fetch_post_payload(
        profile, "https://tamatamo.fanbox.cc/posts/12435068", "12435068"
    )
    assert page.visited == ["https://www.fanbox.cc/"]
    assert payload["body"]["id"] == "12435068"
