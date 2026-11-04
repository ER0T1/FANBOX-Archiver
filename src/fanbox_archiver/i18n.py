"""Interface translation catalogs shared by the CLI and the dynamic reader / desktop app.

Boundaries (see the Anytype i18n decision):

* Only interface text goes through catalogs. Archived posts, creator names, tags and other
  original content are never translated; machine-readable codes (job status, error codes,
  diagnostic fields) stay stable whatever the display language.
* Traditional Chinese (``zh-Hant``) is the base catalog and the fallback for every missing key;
  a key missing from it too is shown as the key itself so the gap is visible, never blank.
* Messages use ``{name}`` placeholders. A plural message is an object of CLDR categories
  (``one``/``other``…); ``other`` is required and chosen when no better category exists.
* ``qps-ploc`` is a generated pseudo-locale for testing: brackets reveal strings that bypass the
  catalog and padding (~40 %) reveals layouts that cannot grow. It is enabled only from
  ``config.yaml`` or the CLI ``--lang`` option, never offered in the settings UI.
* Catalogs ship inside the package; nothing is fetched at run time.
"""

from __future__ import annotations

import json
import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Literal

BASE_LOCALE = "zh-Hant"
PSEUDO_LOCALE = "qps-ploc"
# Real locales with a catalog; ``auto`` resolves among these. Add a JSON file and its tag here.
SUPPORTED_LOCALES: tuple[str, ...] = (BASE_LOCALE,)
LanguageSetting = Literal["auto", "zh-Hant", "qps-ploc"]
LANGUAGE_SETTINGS: tuple[str, ...] = ("auto", BASE_LOCALE, PSEUDO_LOCALE)

LOCALES_DIR = Path(__file__).with_name("locales")
PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
# Language subtags that mean Traditional Chinese when no script subtag is given.
_HANT_REGIONS = {"tw", "hk", "mo"}

Message = str | dict[str, str]


@lru_cache(maxsize=None)
def _load(locale: str) -> dict[str, Message]:
    path = LOCALES_DIR / f"{locale}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"翻譯目錄格式錯誤：{path.name}")
    return {key: value for key, value in data.items() if not key.startswith("$")}


def _pseudo_text(text: str) -> str:
    # Pad outside placeholders so interpolation keeps working; brackets mark catalogued text.
    # Groups of at most four dots with spaces between, so long messages can wrap like real text
    # (an unbroken run of dots could never wrap and would overflow narrow screens).
    count = max(2, round(len(PLACEHOLDER.sub("", text)) * 0.4))
    padding = " ".join("·" * min(4, count - start) for start in range(0, count, 4))
    return f"［{text}{padding}］"


def _pseudo(message: Message) -> Message:
    if isinstance(message, dict):
        return {category: _pseudo_text(text) for category, text in message.items()}
    return _pseudo_text(message)


def catalog(locale: str) -> dict[str, Message]:
    """The complete catalog of ``locale``: its own messages over the base fallback."""
    base = _load(BASE_LOCALE)
    if locale == PSEUDO_LOCALE:
        return {key: _pseudo(value) for key, value in base.items()}
    if locale == BASE_LOCALE or locale not in SUPPORTED_LOCALES:
        return dict(base)
    return {**base, **_load(locale)}


def match_locale(preferred: Iterable[str]) -> str:
    """Pick the best supported locale for a list of BCP 47 tags (e.g. Accept-Language)."""
    for raw in preferred:
        tag = raw.strip().replace("_", "-").lower()
        if not tag:
            continue
        for supported in SUPPORTED_LOCALES:
            if tag == supported.lower():
                return supported
        parts = tag.split("-")
        if parts[0] == "zh":
            # Simplified Chinese has no catalog yet; only Traditional variants match here.
            if "hant" in parts[1:] or _HANT_REGIONS & set(parts[1:]):
                return BASE_LOCALE
            continue
        for supported in SUPPORTED_LOCALES:
            if supported.lower().split("-")[0] == parts[0]:
                return supported
    return BASE_LOCALE


def resolve_locale(setting: str, preferred: Iterable[str] = ()) -> str:
    """Turn a ``display.language`` setting into the locale actually used."""
    if setting == PSEUDO_LOCALE or setting in SUPPORTED_LOCALES:
        return setting
    return match_locale(preferred)


def system_locales() -> list[str]:
    """The operating system's preferred UI languages, best first (used by ``auto`` outside a browser)."""
    found: list[str] = []
    if sys.platform == "win32":
        try:
            import ctypes

            buffer = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
                found.append(buffer.value)
        except (AttributeError, OSError):
            pass
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name, "").split(".", 1)[0]
        if value and value not in {"C", "POSIX"}:
            found.append(value)
    return found


def intl_locale(locale: str) -> str:
    """Locale for number/date formatting; the pseudo-locale formats like the base locale."""
    return BASE_LOCALE if locale == PSEUDO_LOCALE else locale


def plural_category(count: float, locale: str) -> str:
    # Chinese has no grammatical plural; other locales get the minimal one/other rule
    # until a real catalog needs CLDR data (the browser side uses Intl.PluralRules).
    if intl_locale(locale).startswith("zh"):
        return "other"
    return "one" if count == 1 else "other"


def format_number(value: float, locale: str) -> str:
    del locale  # every shipped locale groups thousands with commas
    return f"{value:,}"


def translate(key: str, locale: str = BASE_LOCALE, /, **params: object) -> str:
    """Translated text of ``key`` with ``{name}`` placeholders filled from ``params``."""
    message = catalog(locale).get(key)
    if message is None:
        return key
    if isinstance(message, dict):
        count = params.get("count", 0)
        category = plural_category(float(count) if isinstance(count, (int, float)) else 0, locale)
        message = message.get(category) or message["other"]
    return PLACEHOLDER.sub(lambda match: _param(params, match.group(1), locale, match.group(0)), message)


def _param(params: dict[str, object], name: str, locale: str, original: str) -> str:
    if name not in params:
        return original
    value = params[name]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return format_number(value, locale)
    return str(value)


class Translator:
    """A locale bound to :func:`translate`, for code that renders many messages."""

    def __init__(self, locale: str):
        self.locale = locale

    def __call__(self, key: str, /, **params: object) -> str:
        return translate(key, self.locale, **params)


def browser_payload(locale: str) -> dict[str, object]:
    """What the dynamic reader loads as ``window.FanboxI18n``."""
    return {"locale": locale, "intl": intl_locale(locale), "base": BASE_LOCALE,
            "messages": catalog(locale)}


def browser_script(locale: str) -> str:
    # ``</`` is escaped so catalog text can never close a surrounding script element.
    data = json.dumps(browser_payload(locale), ensure_ascii=False, sort_keys=True).replace("</", "<\\/")
    return f"window.FanboxI18n = {data};\n"
