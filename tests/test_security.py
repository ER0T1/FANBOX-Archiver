from pathlib import Path

import pytest

from fanbox_archiver.security import confined_path, safe_filename, validate_url


def test_safe_filename_windows_rules():
    assert safe_filename('a<b>:c?.zip') == "a_b__c_.zip"
    assert safe_filename("CON") == "_CON"


def test_confined_path_rejects_traversal(tmp_path: Path):
    with pytest.raises(ValueError):
        confined_path(tmp_path, Path("../escape"))


def test_download_url_allowlist():
    assert validate_url("https://downloads.fanbox.cc/images/post/1/a.png", download=True)
    with pytest.raises(ValueError):
        validate_url("http://downloads.fanbox.cc/a", download=True)
    with pytest.raises(ValueError):
        validate_url("https://example.com/a", download=True)


def test_page_url_allows_official_creator_subdomain_only_over_https():
    assert validate_url("https://tamatamo.fanbox.cc/posts/12435068")
    with pytest.raises(ValueError):
        validate_url("http://tamatamo.fanbox.cc/posts/12435068")
    with pytest.raises(ValueError):
        validate_url("https://fanbox.cc.example.com/posts/12435068")
    with pytest.raises(ValueError):
        validate_url("https://tamatamo.fanbox.cc/file.jpeg", download=True)

