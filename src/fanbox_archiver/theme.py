"""Built-in colour tokens and the safe custom-colour stylesheet of the reader and desktop app.

Custom colours are an allowlist of CSS variable names mapped to ``#rrggbb`` values; nothing
else (selectors, functions, URLs or free text) can reach the generated stylesheet.
"""

from __future__ import annotations

import re

# Order is the editor's order: the 8 base colours, then the 5 status colours.
THEME_COLOR_KEYS: tuple[str, ...] = (
    "bg", "surface", "surface-2", "text", "muted", "line", "accent", "accent-soft",
    "blue", "green", "yellow", "red", "purple",
)
# Older static-site names that must follow their status colour.
THEME_COLOR_ALIASES = {"yellow": "amber", "red": "danger", "green": "success"}
HEX_COLOR = re.compile(r"^#[0-9a-f]{6}$")

# Mirrors web_assets/design-tokens.css (a test keeps them in sync).
THEME_DEFAULTS: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#f4f6f9", "surface": "#ffffff", "surface-2": "#f7f8fb", "text": "#1d2430",
        "muted": "#687181", "line": "#dce1e8", "accent": "#db6611", "accent-soft": "#fff0e3",
        "blue": "#3478c9", "green": "#16855a", "yellow": "#ba7500", "red": "#bd3f45", "purple": "#7657c8",
    },
    "dark": {
        "bg": "#101419", "surface": "#181d24", "surface-2": "#212731", "text": "#eef1f5",
        "muted": "#a4adba", "line": "#343c48", "accent": "#ff983f", "accent-soft": "#35271d",
        "blue": "#74aff3", "green": "#5bd3a0", "yellow": "#f0b754", "red": "#ff858a", "purple": "#b3a0f1",
    },
}


def normalize_colors(values: dict[str, str]) -> dict[str, str]:
    """Validate one mode's overrides: allowlisted names and ``#rrggbb`` only, lower-cased."""
    result: dict[str, str] = {}
    for key, value in values.items():
        if key not in THEME_COLOR_KEYS:
            raise ValueError(f"不支援的顏色名稱：{key}")
        color = str(value).strip().lower()
        if not HEX_COLOR.fullmatch(color):
            raise ValueError(f"顏色必須是 #RRGGBB：{key}")
        result[key] = color
    return result


def custom_theme_css(light: dict[str, str], dark: dict[str, str]) -> str:
    """Stylesheet loaded after design-tokens.css; equal specificity, so later wins."""

    def declarations(values: dict[str, str]) -> str:
        values = normalize_colors(values)  # re-validated here so the CSS can never be injected
        parts = []
        for key in THEME_COLOR_KEYS:
            if key in values:
                parts.append(f"--{key}:{values[key]};")
                if key in THEME_COLOR_ALIASES:
                    parts.append(f"--{THEME_COLOR_ALIASES[key]}:{values[key]};")
        return "".join(parts)

    auto = ':root:is(:not([data-theme]),[data-theme="auto"])'
    css = ["/* FANBOX Archiver custom colours (generated). */\n"]
    for mode, values in (("light", light), ("dark", dark)):
        body = declarations(values)
        if body:
            css.append(f':root[data-theme="{mode}"]{{{body}}}\n')
            css.append(f"@media (prefers-color-scheme:{mode}){{{auto}{{{body}}}}}\n")
    return "".join(css)
