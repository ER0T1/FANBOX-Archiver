import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fanbox_archiver import i18n
from fanbox_archiver.cli import app
from fanbox_archiver.config import AppConfig, StorageConfig
from fanbox_archiver.i18n import (
    BASE_LOCALE, PLACEHOLDER, PSEUDO_LOCALE, browser_script, catalog, match_locale, resolve_locale, translate,
)

PACKAGE = Path(i18n.__file__).parent
runner = CliRunner()


def _placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def test_base_catalog_is_well_formed():
    raw = json.loads((PACKAGE / "locales" / "zh-Hant.json").read_text(encoding="utf-8"))
    messages = catalog(BASE_LOCALE)
    assert messages and "$comment" in raw and "$comment" not in messages
    for key, value in messages.items():
        assert re.fullmatch(r"[a-z0-9_]+(\.[a-z0-9_]+)+", key), key
        if isinstance(value, dict):
            assert "other" in value, key
            assert set(value) <= {"zero", "one", "two", "few", "many", "other"}, key
            # Every plural form offers the same placeholders, so callers never lose a value.
            assert len({frozenset(_placeholders(text)) for text in value.values()}) == 1, key
        else:
            assert isinstance(value, str) and value.strip(), key


def _used_keys() -> set[str]:
    sources = [*(PACKAGE / "web_src").glob("*.ts"), PACKAGE / "site_assets" / "app.js",
               PACKAGE / "cli.py", PACKAGE / "indexer.py"]
    keys: set[str] = set()
    for path in sources:
        text = path.read_text(encoding="utf-8")
        keys |= set(re.findall(r"""\bt\(\s*["']([a-z0-9_]+(?:\.[a-z0-9_]+)+)["']""", text))
    html = (PACKAGE / "web_assets" / "index.html").read_text(encoding="utf-8")
    keys |= set(re.findall(r'data-i18n="([^"]+)"', html))
    for attributes in re.findall(r'data-i18n-attr="([^"]+)"', html):
        keys |= {pair.split(":", 1)[1] for pair in attributes.split(";")}
    # Keys chosen by an expression (search placeholders) are listed as plain string literals.
    keys |= set(re.findall(r'"(search\.[a-z_]+)"', (PACKAGE / "web_src" / "controls.ts").read_text(encoding="utf-8")))
    return keys


def test_every_key_used_by_the_ui_cli_and_static_site_exists():
    used = _used_keys()
    assert {"nav.posts", "posts.total", "static.nav_posts", "cli.status.last_run", "search.creators"} <= used
    assert sorted(used - set(catalog(BASE_LOCALE))) == []


def test_translate_interpolates_formats_numbers_and_keeps_gaps_visible():
    assert translate("posts.total", BASE_LOCALE, count=1234) == "1,234 篇備份"
    assert translate("common.page_position", BASE_LOCALE, page=2, pages=3) == "目前第 2 頁，共 3 頁"
    # A post ID is an identifier, never a grouped number.
    assert "Post 12345" in translate("posts.card_meta", BASE_LOCALE, creator="A", post_id="12345", count=2)
    assert translate("no.such.key", BASE_LOCALE) == "no.such.key"
    assert translate("common.page_position", BASE_LOCALE, page=1) == "目前第 1 頁，共 {pages} 頁"


def test_pseudo_locale_marks_and_pads_every_message_but_keeps_placeholders():
    base, pseudo = catalog(BASE_LOCALE), catalog(PSEUDO_LOCALE)
    assert set(base) == set(pseudo)
    for key, value in base.items():
        forms = value if isinstance(value, dict) else {"other": value}
        pseudo_forms = pseudo[key] if isinstance(pseudo[key], dict) else {"other": pseudo[key]}
        for category, text in forms.items():
            marked = pseudo_forms[category]
            assert marked.startswith("［") and marked.endswith("］"), key
            assert len(marked) >= len(text) + 4, key
            assert _placeholders(marked) == _placeholders(text), key
    assert translate("posts.total", PSEUDO_LOCALE, count=3).startswith("［3 篇備份")


def test_missing_translations_fall_back_to_traditional_chinese(tmp_path: Path, monkeypatch):
    (tmp_path / "zh-Hant.json").write_text(
        (PACKAGE / "locales" / "zh-Hant.json").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "en.json").write_text(json.dumps({"nav.posts": "Posts"}), encoding="utf-8")
    monkeypatch.setattr(i18n, "LOCALES_DIR", tmp_path)
    monkeypatch.setattr(i18n, "SUPPORTED_LOCALES", (BASE_LOCALE, "en"))
    i18n._load.cache_clear()
    try:
        assert translate("nav.posts", "en") == "Posts"
        assert translate("nav.creators", "en") == "創作者"  # not translated yet → base text
        assert match_locale(["en-US"]) == "en"
        assert i18n.plural_category(1, "en") == "one"
    finally:
        i18n._load.cache_clear()


@pytest.mark.parametrize(("preferred", "expected"), [
    (["zh-TW"], BASE_LOCALE), (["zh_HK"], BASE_LOCALE), (["zh-Hant-TW"], BASE_LOCALE),
    (["en-US", "ja"], BASE_LOCALE), ([], BASE_LOCALE), (["", "zh-hant"], BASE_LOCALE),
])
def test_auto_language_matches_supported_locales_or_falls_back(preferred, expected):
    assert match_locale(preferred) == expected
    assert resolve_locale("auto", preferred) == expected


def test_explicit_language_settings_win_over_the_system():
    assert resolve_locale("zh-Hant", ["en-US"]) == BASE_LOCALE
    assert resolve_locale(PSEUDO_LOCALE, ["zh-TW"]) == PSEUDO_LOCALE


def test_browser_script_cannot_close_a_script_element():
    script = browser_script(BASE_LOCALE)
    assert script.startswith("window.FanboxI18n = {") and "</" not in script
    payload = json.loads(script[len("window.FanboxI18n = "):].rstrip().rstrip(";"))
    assert payload["locale"] == BASE_LOCALE and payload["messages"]["nav.posts"] == "投稿"
    assert json.loads(browser_script(PSEUDO_LOCALE)[len("window.FanboxI18n = "):].rstrip()[:-1])["intl"] == BASE_LOCALE


def _status_config(tmp_path: Path, language: str = "auto") -> Path:
    config = AppConfig(storage=StorageConfig(output_dir=tmp_path / "FANBOX", database=tmp_path / "FANBOX" / "backup.db"))
    config.display.language = language  # type: ignore[assignment]
    path = tmp_path / "config.yaml"
    AppConfig.save_editable(path, config, {})  # a new file gets the whole config
    return path


def test_cli_status_follows_the_config_language_and_the_lang_option(tmp_path: Path):
    path = _status_config(tmp_path)
    default = runner.invoke(app, ["status", "--config", str(path)])
    assert default.exit_code == 0, default.output
    assert "尚無備份紀錄。" in default.output and "［" not in default.output

    pseudo = runner.invoke(app, ["--lang", "qps-ploc", "status", "--config", str(path)])
    assert pseudo.exit_code == 0, pseudo.output
    assert "［尚無備份紀錄。" in pseudo.output

    configured = runner.invoke(app, ["status", "--config", str(_status_config(tmp_path / "p", "qps-ploc"))])
    assert "［尚無備份紀錄。" in configured.output

    invalid = runner.invoke(app, ["--lang", "xx", "status", "--config", str(path)])
    assert invalid.exit_code != 0
