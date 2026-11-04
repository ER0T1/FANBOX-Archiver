import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from fanbox_archiver.config import AppConfig
from fanbox_archiver.theme import THEME_COLOR_KEYS, THEME_DEFAULTS, custom_theme_css

TOKENS = Path(__file__).parents[1] / "src/fanbox_archiver/web_assets/design-tokens.css"


def _block(css: str, selector: str) -> dict[str, str]:
    body = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css).group(1)
    return dict(re.findall(r"--([\w-]+)\s*:\s*(#[0-9a-fA-F]{3,6})", body))


def _hex6(value: str) -> str:
    value = value.lower()
    return "#" + "".join(ch * 2 for ch in value[1:]) if len(value) == 4 else value


def test_theme_defaults_match_the_design_tokens():
    css = TOKENS.read_text(encoding="utf-8")
    for mode, selector in (("light", ":root"), ("dark", ':root[data-theme="dark"]')):
        tokens = {key: _hex6(value) for key, value in _block(css, selector).items()}
        assert {key: tokens[key] for key in THEME_COLOR_KEYS} == THEME_DEFAULTS[mode], mode


def test_custom_css_covers_forced_and_system_modes_and_aliases():
    css = custom_theme_css({"yellow": "#123456"}, {"accent": "#ABCDEF"})
    assert ':root[data-theme="light"]{--yellow:#123456;--amber:#123456;}' in css
    assert '@media (prefers-color-scheme:light){:root:is(:not([data-theme]),[data-theme="auto"]){--yellow:#123456;' in css
    assert ':root[data-theme="dark"]{--accent:#abcdef;}' in css
    assert custom_theme_css({}, {}).count("{") == 0


@pytest.mark.parametrize("colors", [
    {"light": {"accent": "red"}},
    {"light": {"accent": "#12345"}},
    {"light": {"accent": "#000000;}body{background:url(https://x)"}},
    {"light": {"font-family": "#000000"}},
    {"light": {"accent;}*{": "#000000"}},
    {"sepia": {}},
])
def test_custom_colors_only_accept_allowlisted_hex(colors):
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"display": {"colors": colors}})


def test_custom_css_revalidates_its_input():
    with pytest.raises(ValueError):
        custom_theme_css({"accent": "#000000;}*{color:red"}, {})
