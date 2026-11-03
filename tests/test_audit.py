import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

import fanbox_archiver.cli as cli
from fanbox_archiver.audit import ArchiveAuditor
from fanbox_archiver.config import AppConfig, StorageConfig
from fanbox_archiver.models import ContentBlock, CreatorProfile, Post
from fanbox_archiver.parser import fingerprint
from fanbox_archiver.service import ArchiveService


runner = CliRunner()


def configured(tmp_path: Path) -> AppConfig:
    root = tmp_path / "archive"
    return AppConfig(storage=StorageConfig(output_dir=root, database=root / "backup.db"))


def make_post(title: str) -> Post:
    post = Post(
        post_id="42", creator_id="alice", creator_name="Alice", title=title,
        published_at=datetime(2026, 11, 1, tzinfo=UTC),
        updated_at=datetime(2026, 11, 2, tzinfo=UTC),
        url="https://www.fanbox.cc/@alice/posts/42",
        blocks=[ContentBlock(type="paragraph", text=title)],
    )
    post.content_fingerprint = fingerprint(post)
    return post


def make_profile(description: str) -> CreatorProfile:
    profile = CreatorProfile(
        creator_id="alice", name="Alice", description=description,
        fanbox_url="https://www.fanbox.cc/@alice",
    )
    profile.content_fingerprint = profile.calculate_fingerprint()
    return profile


def test_audit_detects_tama_style_reversed_history_without_mutating_archive(tmp_path: Path):
    config = configured(tmp_path)
    service = ArchiveService(config)
    service.save_profile(make_profile("A"))
    service.save_profile(make_profile("B"))
    rows = service.db.profile_versions("alice")
    with service.db.connect() as db:
        db.execute(
            "UPDATE creator_profile_versions SET captured_at=? WHERE profile_version_id=?",
            ("2026-11-02T15:00:00+00:00", rows[0]["profile_version_id"]),
        )
        db.execute(
            "UPDATE creator_profile_versions SET captured_at=? WHERE profile_version_id=?",
            ("2026-11-01T15:00:00+00:00", rows[1]["profile_version_id"]),
        )
        db.execute(
            "UPDATE creators SET latest_profile_version_id=? WHERE creator_id='alice'",
            (rows[0]["profile_version_id"],),
        )

    before = config.storage.database.read_bytes()
    before_mtime = config.storage.database.stat().st_mtime_ns
    report = ArchiveAuditor(config).run()

    codes = {finding.code for finding in report.findings}
    assert {"capture_order", "manifest_captured_at", "latest_pointer"} <= codes
    assert report.read_only is True
    assert config.storage.database.read_bytes() == before
    assert config.storage.database.stat().st_mtime_ns == before_mtime
    serialized = report.model_dump_json()
    assert str(tmp_path) not in serialized
    assert "2026-11-02T15:00:00" not in serialized


def test_audit_generates_dry_run_plan_for_deterministic_pointer_and_alias_repairs(tmp_path: Path):
    config = configured(tmp_path)
    service = ArchiveService(config)
    service.save(make_post("A"))
    service.save(make_post("B"))
    rows = service.db.version_rows("42")
    with service.db.connect() as db:
        db.execute(
            "UPDATE posts SET latest_version_id=? WHERE post_id='42'",
            (rows[0]["version_id"],),
        )
    root = Path(str(service.db.post_row("42")["local_path"]))
    (root / "post.json").unlink()
    (root / "post.json").write_bytes((Path(str(rows[0]["local_path"])) / "post.json").read_bytes())

    report = ArchiveAuditor(config).run()

    automatic = {finding.code for finding in report.findings if finding.repairability == "automatic"}
    assert {"latest_pointer", "latest_alias"} <= automatic
    assert {action.finding_code for action in report.repair_plan} >= {
        "latest_pointer", "latest_alias",
    }
    assert all(action.dry_run for action in report.repair_plan)


def test_audit_reports_naive_timestamp_without_echoing_value(tmp_path: Path):
    config = configured(tmp_path)
    service = ArchiveService(config)
    with service.db.connect() as db:
        db.execute(
            "INSERT INTO backup_runs(started_at,scope) VALUES(?,?)",
            ("2026-11-03T12:34:56", "supporting"),
        )

    report = ArchiveAuditor(config).run()
    finding = next(item for item in report.findings if item.code == "timestamp_naive")
    assert finding.evidence == "source: backup_runs.started_at"
    assert "12:34:56" not in report.model_dump_json()


def test_clean_archive_and_manifest_database_timestamps_are_consistent(tmp_path: Path):
    config = configured(tmp_path)
    service = ArchiveService(config)
    service.save(make_post("A"))
    service.save_profile(make_profile("Profile"))
    service.db.record_supporting_creators([("alice", "Alice")])
    service.save_fancard({"body": {
        "plan": {"creatorId": "alice", "title": "Plan", "fee": 100},
        "supportTransactions": [{"targetMonth": "2026-11", "paidAmount": 100}],
    }}, None, None)

    report = ArchiveAuditor(config).run()

    assert report.findings == []
    assert report.repair_plan == []


def test_audit_reports_version_gap_and_orphan_directory_once(tmp_path: Path):
    config = configured(tmp_path)
    service = ArchiveService(config)
    service.save(make_post("A"))
    service.save(make_post("B"))
    rows = service.db.version_rows("42")
    with service.db.connect() as db:
        db.execute("UPDATE posts SET latest_version_id=? WHERE post_id='42'", (rows[1]["version_id"],))
        db.execute("DELETE FROM post_versions WHERE version_id=?", (rows[0]["version_id"],))

    report = ArchiveAuditor(config).run()

    assert any(item.code == "version_sequence" for item in report.findings)
    orphans = [item for item in report.findings if item.code == "orphan_version_directory"]
    assert len(orphans) == 1


def test_audit_missing_database_is_read_only_and_cli_json_has_no_absolute_path(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    archive = tmp_path / "does-not-exist"
    config_path.write_text(
        "storage:\n"
        f"  output_dir: '{archive.as_posix()}'\n"
        f"  database: '{(archive / 'backup.db').as_posix()}'\n",
        encoding="utf-8",
    )

    result = runner.invoke(cli.app, ["audit", "--json", "--config", str(config_path)])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["read_only"] is True
    assert payload["findings"][0]["code"] == "database_missing"
    assert not archive.exists()
    assert str(tmp_path) not in result.output
