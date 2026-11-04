import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone

import pytest
import yaml

from fanbox_archiver.markdown import render_markdown
from fanbox_archiver.models import Post
from fanbox_archiver import timestamps
from fanbox_archiver.timestamps import format_display, isoformat_display, parse_instant


@pytest.mark.parametrize(("value", "human", "iso"), [
    ("2026-11-02T15:59:59+00:00", "2026年11月02日 23:59", "2026-11-02T23:59:59+08:00"),
    ("2026-11-02T16:00:00Z", "2026年11月03日 00:00", "2026-11-03T00:00:00+08:00"),
    ("2026-11-03T01:00:00+09:00", "2026年11月03日 00:00", "2026-11-03T00:00:00+08:00"),
    ("2026-11-03T00:00:00+08:00", "2026年11月03日 00:00", "2026-11-03T00:00:00+08:00"),
    (datetime(2026, 12, 31, 16, tzinfo=UTC), "2027年01月01日 00:00", "2027-01-01T00:00:00+08:00"),
])
def test_time_points_cross_taipei_midnight_consistently(value, human, iso):
    assert format_display(value) == human
    assert isoformat_display(value) == iso


def test_naive_and_invalid_values_are_never_guessed():
    assert parse_instant("2026-11-02T16:00:00") is None
    assert format_display("2026-11-02T16:00:00") == "2026-11-02T16:00:00（時區未標示）"
    assert isoformat_display(datetime(2026, 11, 2)) == "2026-11-02T00:00:00（時區未標示）"
    assert format_display("not a date") == "not a date"
    assert format_display(None) == "-"
    assert isoformat_display("", None) is None


def test_a_chosen_timezone_ignores_the_host_timezone():
    # The host clock is set to Tokyo; an explicit Asia/Taipei setting must still win.
    script = (
        "import json, fanbox_archiver.cli as cli; from fanbox_archiver import timestamps as t;"
        "t.set_display_timezone('Asia/Taipei');"
        "v='2026-11-02T16:00:00+00:00'; print(json.dumps([cli.format_local_time(v), t.format_display(v)]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], env={**os.environ, "TZ": "JST-9"},
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    assert result.stdout.strip() == json.dumps(["2026-11-03T00:00:00+08:00", "2026年11月03日 00:00"])


def test_tokyo_setting_changes_display_cli_and_markdown_without_touching_values():
    timestamps.set_display_timezone("Asia/Tokyo")
    value = "2026-11-02T15:30:00+00:00"
    assert format_display(value) == "2026年11月03日 00:30"
    assert isoformat_display(value) == "2026-11-03T00:30:00+09:00"
    import fanbox_archiver.cli as cli
    assert cli.format_local_time(value) == "2026-11-03T00:30:00+09:00"
    post = Post(post_id="1", creator_id="alice", title="t", url="https://alice.fanbox.cc/posts/1",
                published_at=datetime(2026, 11, 2, 15, 30, tzinfo=UTC))
    metadata = yaml.safe_load(render_markdown(post).split("---")[1])
    assert metadata["published_at"] == "2026-11-03T00:30:00+09:00"


def test_system_timezone_resolution_and_fallback(monkeypatch):
    assert timestamps.resolve_timezone("system", system_name=lambda: "Asia/Tokyo").name == "Asia/Tokyo"
    unknown = timestamps.resolve_timezone("system", system_name=lambda: None)
    assert unknown.setting == "system" and unknown.notice and "UTC 時差" in unknown.notice
    monkeypatch.setattr(timestamps._time, "localtime", lambda: type("T", (), {"tm_gmtoff": 9 * 3600})())
    assert timestamps.resolve_timezone("system", system_name=lambda: "Not/AZone").name == "Etc/GMT-9"
    assert timestamps.resolve_timezone("Asia/Tokyo").notice is None
    with pytest.raises(ValueError):
        timestamps.resolve_timezone("Mars/Olympus")
    assert {"Asia/Taipei", "Asia/Tokyo"} <= set(timestamps.timezone_names())


def test_markdown_front_matter_uses_taipei_offsets():
    jst = timezone(timedelta(hours=9))
    post = Post(
        post_id="1", creator_id="alice", title="Midnight", url="https://alice.fanbox.cc/posts/1",
        published_at=datetime(2026, 11, 3, 0, 30, tzinfo=jst),
        updated_at=datetime(2026, 11, 3, 1, 0, tzinfo=jst),
    )
    output = render_markdown(post, archive_version=1, captured_at="2026-11-02T16:00:00+00:00")
    metadata = yaml.safe_load(output.split("---")[1])
    assert metadata["published_at"] == "2026-11-02T23:30:00+08:00"
    assert metadata["updated_at"] == "2026-11-03T00:00:00+08:00"
    assert metadata["captured_at"] == "2026-11-03T00:00:00+08:00"


def test_display_dates_use_shared_contract():
    assert timestamps.format_display("2026-11-02T16:00:00+00:00") == "2026年11月03日 00:00"
    assert timestamps.format_display("2026-11-02T16:00:00") == "2026-11-02T16:00:00（時區未標示）"
