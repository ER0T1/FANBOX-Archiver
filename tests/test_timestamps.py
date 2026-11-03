import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone

import pytest
import yaml

from fanbox_archiver.indexer import IndexBuilder
from fanbox_archiver.markdown import render_markdown
from fanbox_archiver.models import Post
from fanbox_archiver.timestamps import format_taipei, isoformat_taipei, parse_instant


@pytest.mark.parametrize(("value", "human", "iso"), [
    ("2026-11-02T15:59:59+00:00", "2026年11月02日 23:59", "2026-11-02T23:59:59+08:00"),
    ("2026-11-02T16:00:00Z", "2026年11月03日 00:00", "2026-11-03T00:00:00+08:00"),
    ("2026-11-03T01:00:00+09:00", "2026年11月03日 00:00", "2026-11-03T00:00:00+08:00"),
    ("2026-11-03T00:00:00+08:00", "2026年11月03日 00:00", "2026-11-03T00:00:00+08:00"),
    (datetime(2026, 12, 31, 16, tzinfo=UTC), "2027年01月01日 00:00", "2027-01-01T00:00:00+08:00"),
])
def test_time_points_cross_taipei_midnight_consistently(value, human, iso):
    assert format_taipei(value) == human
    assert isoformat_taipei(value) == iso


def test_naive_and_invalid_values_are_never_guessed():
    assert parse_instant("2026-11-02T16:00:00") is None
    assert format_taipei("2026-11-02T16:00:00") == "2026-11-02T16:00:00（時區未標示）"
    assert isoformat_taipei(datetime(2026, 11, 2)) == "2026-11-02T00:00:00（時區未標示）"
    assert format_taipei("not a date") == "not a date"
    assert format_taipei(None) == "-"
    assert isoformat_taipei("", None) is None


def test_output_does_not_depend_on_host_timezone():
    script = (
        "import json, fanbox_archiver.cli as cli; from fanbox_archiver.timestamps import format_taipei;"
        "v='2026-11-02T16:00:00+00:00'; print(json.dumps([cli.format_local_time(v), format_taipei(v)]))"
    )
    outputs = set()
    for zone in ("UTC0", "PST8PDT", "JST-9"):
        result = subprocess.run(
            [sys.executable, "-c", script], env={**os.environ, "TZ": zone},
            capture_output=True, text=True, encoding="utf-8", check=True,
        )
        outputs.add(result.stdout.strip())
    assert outputs == {json.dumps(["2026-11-03T00:00:00+08:00", "2026年11月03日 00:00"])}


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


def test_static_index_dates_use_shared_contract():
    assert IndexBuilder._date("2026-11-02T16:00:00+00:00") == "2026年11月03日 00:00"
    assert IndexBuilder._date("2026-11-02T16:00:00") == "2026-11-02T16:00:00（時區未標示）"
