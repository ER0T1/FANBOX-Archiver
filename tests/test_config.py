import shutil
from pathlib import Path

import yaml

from fanbox_archiver.config import AppConfig
from fanbox_archiver.config_contract import (
    ExampleSpec,
    check_example,
    check_registered_examples,
    model_field_paths,
    registered_fields,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_config_uses_defaults_without_forced_rewrite(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("sync:\n  max_posts_per_run: 31\n", encoding="utf-8")

    config = AppConfig.load(path)

    assert config.sync.max_posts_per_run == 31
    assert config.backup_defaults.dry_run is False
    assert config.backup_defaults.include_profile is True
    assert config.backup_defaults.include_fancard is True
    assert "backup_defaults" not in path.read_text(encoding="utf-8")
    updated = config.with_editable_patch({"logging": {"level": "debug"}})

    AppConfig.save_editable(path, updated, {"logging": {"level": "debug"}})

    text = path.read_text(encoding="utf-8")
    assert "backup_defaults" not in text
    assert "level: DEBUG" in text


def test_config_example_matches_all_model_fields_and_defaults():
    reports = check_registered_examples(PROJECT_ROOT)

    assert len(reports) == 1
    assert reports[0].passed, "\n".join(reports[0].lines())
    assert "download.timeout_seconds" in model_field_paths(AppConfig)
    assert "backup_defaults.include_fancard" in model_field_paths(AppConfig)


def test_config_contract_reports_missing_extra_and_misplaced_fields(tmp_path: Path):
    raw = AppConfig().model_dump(mode="json")
    timeout = raw["download"].pop("timeout_seconds")
    raw["timeout_seconds"] = timeout
    path = tmp_path / "sample.example.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    spec = ExampleSpec(
        relative_path=Path(path.name), format="yaml",
        field_source=lambda: model_field_paths(AppConfig), model=AppConfig,
    )

    report = check_example(tmp_path, spec)

    assert report.missing == ("download.timeout_seconds",)
    assert report.extra == ("timeout_seconds",)
    assert "download.timeout_seconds" in "\n".join(report.lines())


def test_secret_contract_never_echoes_secret_values(tmp_path: Path):
    secret = "private-cookie-must-not-appear"
    (tmp_path / ".env.example").write_text(f"FANBOX_COOKIE={secret}\n", encoding="utf-8")
    spec = ExampleSpec(
        relative_path=Path(".env.example"), format="env",
        field_source=registered_fields("FANBOX_COOKIE"),
        secret_placeholders={"FANBOX_COOKIE": frozenset({""})},
    )

    report = check_example(tmp_path, spec)
    output = "\n".join(report.lines())

    assert report.unsafe_secrets == ("FANBOX_COOKIE",)
    assert "FANBOX_COOKIE" in output
    assert secret not in output


def test_clean_environment_smoke_paths(tmp_path: Path):
    missing = tmp_path / "missing.yaml"
    empty = tmp_path / "empty.yaml"
    copied = tmp_path / "config.yaml"
    empty.write_text("{}\n", encoding="utf-8")
    shutil.copy2(PROJECT_ROOT / "config.example.yaml", copied)

    missing_config = AppConfig.load(missing)
    empty_config = AppConfig.load(empty)
    copied_config = AppConfig.load(copied)

    assert missing_config.model_dump() == empty_config.model_dump()
    assert copied_config.model_dump() == empty_config.model_dump()
    assert not missing.exists()
    assert empty.read_text(encoding="utf-8") == "{}\n"


def test_existing_config_with_taipei_schedule_keeps_taipei_display(tmp_path):
    import yaml
    from fanbox_archiver.config import AppConfig

    old = tmp_path / "old.yaml"
    old.write_text("schedule:\n  enabled: true\n  time: '03:00'\n  timezone: Asia/Taipei\n", encoding="utf-8")
    assert AppConfig.load(old).display.timezone == "Asia/Taipei"
    assert yaml.safe_load(old.read_text(encoding="utf-8"))["display"] == {"timezone": "Asia/Taipei"}
    assert AppConfig.load(old).schedule.time == "03:00"

    fresh = tmp_path / "fresh.yaml"
    fresh.write_text("{}\n", encoding="utf-8")
    assert AppConfig.load(fresh).display.timezone == "system"
    assert AppConfig().display.timezone == "system"

    chosen = tmp_path / "chosen.yaml"
    chosen.write_text("display:\n  timezone: Asia/Tokyo\nschedule:\n  timezone: Asia/Taipei\n", encoding="utf-8")
    assert AppConfig.load(chosen).display.timezone == "Asia/Tokyo"


def test_invalid_display_timezone_is_rejected():
    import pytest
    from pydantic import ValidationError
    from fanbox_archiver.config import AppConfig

    with pytest.raises(ValidationError):
        AppConfig.model_validate({"display": {"timezone": "Mars/Olympus"}})
