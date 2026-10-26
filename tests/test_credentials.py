import pytest

from fanbox_archiver.browser_session import cookies_to_header
from fanbox_archiver.credentials import _reject_header_injection


def test_cookie_header_rejects_newlines():
    with pytest.raises(ValueError):
        _reject_header_injection("a=b\r\nX-Evil: yes")


def test_browser_profile_only_exports_fanbox_cookies():
    header = cookies_to_header([
        {"name": "a", "value": "1", "domain": ".fanbox.cc"},
        {"name": "b", "value": "2", "domain": "api.fanbox.cc"},
        {"name": "secret", "value": "no", "domain": ".example.com"},
    ])
    assert header == "a=1; b=2"
