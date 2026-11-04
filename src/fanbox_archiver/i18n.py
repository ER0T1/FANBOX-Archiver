"""Interface translation catalogs shared by the CLI and the dynamic reader / desktop app.

Boundaries (see the Anytype i18n decision):

* Only interface text goes through catalogs. Archived posts, creator names, tags and other
  original content are never translated; machine-readable codes (job status, error codes,
  diagnostic fields) stay stable whatever the display language.
* Traditional Chinese (``zh-Hant``) is the base catalog and the fallback for every missing key;
  a key missing from it too is shown as the key itself so the gap is visible, never blank.
  ``auto`` picks among English, Japanese, Korean and Traditional Chinese (any ``zh-*``) and uses
  English when the system or browser asks for none of them.
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
# ``auto`` uses this when none of the system or browser languages has a catalog.
FALLBACK_LOCALE = "en"
# Real locales with a catalog; ``auto`` resolves among these. Add a JSON file and its tag here
# (and to ``LanguageSetting``); release:check requires every catalog to have the base keys.
SUPPORTED_LOCALES: tuple[str, ...] = (BASE_LOCALE, "en", "ja", "ko")
LanguageSetting = Literal["auto", "zh-Hant", "en", "ja", "ko", "qps-ploc"]
LANGUAGE_SETTINGS: tuple[str, ...] = ("auto", *SUPPORTED_LOCALES, PSEUDO_LOCALE)
# Locales without grammatical plural; their plural messages only need ``other``.
_NO_PLURAL = ("zh", "ja", "ko")

LOCALES_DIR = Path(__file__).with_name("locales")
PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
# English month names and ordinals for ``common.datetime`` (e.g. "October 29th, 2026 20:28").
# Fixed tables rather than the host locale, so output never depends on the machine.
_MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August",
                "September", "October", "November", "December")

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
        # Language match ignoring region and script: every Chinese variant (Simplified readers
        # included) reads the Traditional catalog more easily than the English fallback.
        language = tag.split("-")[0]
        for supported in SUPPORTED_LOCALES:
            if supported.lower().split("-")[0] == language:
                return supported
    return FALLBACK_LOCALE


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
    # The CLDR cardinal rules of the shipped locales: Chinese, Japanese and Korean have no
    # grammatical plural; English uses "one" for exactly 1 (the browser uses Intl.PluralRules).
    if intl_locale(locale).split("-")[0] in _NO_PLURAL:
        return "other"
    return "one" if count == 1 else "other"


def ordinal_en(day: int) -> str:
    """English ordinal day: 1st, 2nd, 3rd, 4th … 11th, 12th, 13th … 21st."""
    suffix = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def datetime_params(year: int, month: int, day: int, hour: int, minute: int) -> dict[str, str]:
    """Parameters of ``common.datetime``; each catalog picks the ones its format uses."""
    return {"year": f"{year:04d}", "month": f"{month:02d}", "day": f"{day:02d}", "hour": f"{hour:02d}",
            "minute": f"{minute:02d}", "month_name": _MONTH_NAMES[month - 1], "day_ordinal": ordinal_en(day)}


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


class Text(str):
    """Interface text produced where the reader's language is unknown (core code, background work).

    It *is* the base-language string, so logs, comparisons and existing callers keep working, and
    it remembers its key and parameters so a boundary that knows the language (the web server, the
    CLI) can show it translated with :func:`localize`. Parameters may themselves be ``Text``.
    """

    key: str
    params: dict[str, object]

    def __new__(cls, key: str, /, **params: object) -> Text:
        self = super().__new__(cls, translate(key, BASE_LOCALE, **params))
        self.key = key
        self.params = params
        return self

    def __reduce__(self):  # copy/deepcopy/pickle rebuild from the key, not the rendered text
        return (_rebuild_text, (self.key, self.params))

    def localized(self, locale: str) -> str:
        return translate(self.key, locale, **{name: localize(value, locale) for name, value in self.params.items()})

    def encode(self) -> str:
        """A string for storage that :func:`decode_text` turns back into ``Text``."""
        return STORED_TEXT_PREFIX + json.dumps(_dump_text(self), ensure_ascii=False)


STORED_TEXT_PREFIX = "i18n:"


def _rebuild_text(key: str, params: dict[str, object]) -> Text:
    return Text(key, **params)


def _dump_text(value: object) -> object:
    if isinstance(value, Text):
        return {"$key": value.key, "params": {name: _dump_text(item) for name, item in value.params.items()}}
    return value


def _load_text(value: object) -> object:
    if isinstance(value, dict) and isinstance(value.get("$key"), str):
        params = value.get("params") if isinstance(value.get("params"), dict) else {}
        return Text(value["$key"], **{name: _load_text(item) for name, item in params.items()})
    return value


def decode_text(value: object) -> object:
    """Undo :meth:`Text.encode`; anything else (older plain text, None) is returned unchanged."""
    if isinstance(value, str) and value.startswith(STORED_TEXT_PREFIX):
        try:
            loaded = _load_text(json.loads(value[len(STORED_TEXT_PREFIX):]))
        except ValueError:
            return value
        return loaded if isinstance(loaded, Text) else value
    return value


def encode_texts(value: object) -> object:
    """``value`` (e.g. job event data) with every ``Text`` replaced by its stored form, for JSON."""
    if isinstance(value, Text):
        return value.encode()
    if isinstance(value, dict):
        return {name: encode_texts(item) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode_texts(item) for item in value]
    return value


def decode_texts(value: object) -> object:
    """Undo :func:`encode_texts` after reading the JSON back."""
    if isinstance(value, str):
        return decode_text(value)
    if isinstance(value, dict):
        return {name: decode_texts(item) for name, item in value.items()}
    if isinstance(value, list):
        return [decode_texts(item) for item in value]
    return value


def error_text(exc: BaseException) -> str:
    """An exception's message, keeping it translatable when it was raised with ``Text``."""
    return exc.args[0] if len(exc.args) == 1 and isinstance(exc.args[0], Text) else str(exc)


def localize(value: object, locale: str) -> object:
    """``value`` with every ``Text`` (also inside dicts, lists and tuples) shown in ``locale``."""
    if isinstance(value, Text):
        return value.localized(locale)
    if isinstance(value, dict):
        return {name: localize(item, locale) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [localize(item, locale) for item in value]
    return value


def browser_payload(locale: str) -> dict[str, object]:
    """What the dynamic reader loads as ``window.FanboxI18n``."""
    return {"locale": locale, "intl": intl_locale(locale), "base": BASE_LOCALE,
            "messages": catalog(locale)}


def browser_script(locale: str) -> str:
    # ``</`` is escaped so catalog text can never close a surrounding script element.
    data = json.dumps(browser_payload(locale), ensure_ascii=False, sort_keys=True).replace("</", "<\\/")
    return f"window.FanboxI18n = {data};\n"
