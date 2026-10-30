from pathlib import Path

from fanbox_archiver.config import AppConfig


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
