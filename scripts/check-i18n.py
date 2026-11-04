"""Catalog consistency guard for the interface languages (run by `npm run release:check`).

Every shipped locale must have exactly the keys of the base catalog (zh-Hant), the same
`{placeholders}` (the date format may use the English month-name / ordinal values instead
of the numeric month and day), and the same plural shape with an `other` form. English
plural messages also need `one`. The English catalog must not contain Chinese, Japanese or
Korean script, which is how an untranslated copy usually shows up.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fanbox_archiver.i18n import BASE_LOCALE, LOCALES_DIR, PLACEHOLDER, SUPPORTED_LOCALES  # noqa: E402

# Values the date formatter provides beyond the base format's own placeholders.
EXTRA_PLACEHOLDERS = {"common.datetime": {"month_name", "day_ordinal"}}
OPTIONAL_PLACEHOLDERS = {"common.datetime": {"month", "day"}}
CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯豈-﫿]")


def _load(locale: str) -> dict[str, object]:
    data = json.loads((LOCALES_DIR / f"{locale}.json").read_text(encoding="utf-8"))
    return {key: value for key, value in data.items() if not key.startswith("$")}


def _holders(value: object) -> set[str]:
    texts = value.values() if isinstance(value, dict) else [value]
    return set().union(*(set(PLACEHOLDER.findall(str(text))) for text in texts))


def problems() -> list[str]:
    found: list[str] = []
    base = _load(BASE_LOCALE)
    shipped = sorted(path.stem for path in LOCALES_DIR.glob("*.json"))
    if shipped != sorted(SUPPORTED_LOCALES):
        found.append(f"catalog files {shipped} differ from SUPPORTED_LOCALES {sorted(SUPPORTED_LOCALES)}")
    for locale in SUPPORTED_LOCALES:
        if locale == BASE_LOCALE:
            continue
        messages = _load(locale)
        for key in sorted(set(base) - set(messages)):
            found.append(f"{locale}: missing {key}")
        for key in sorted(set(messages) - set(base)):
            found.append(f"{locale}: unknown key {key}")
        for key in sorted(set(base) & set(messages)):
            want, value = base[key], messages[key]
            if isinstance(want, dict) != isinstance(value, dict):
                found.append(f"{locale}: {key} plural shape differs from {BASE_LOCALE}")
                continue
            if isinstance(value, dict):
                if "other" not in value:
                    found.append(f"{locale}: {key} plural message needs 'other'")
                if locale == "en" and set(value) != {"one", "other"}:
                    found.append(f"{locale}: {key} English plural message needs 'one' and 'other'")
            elif not str(value).strip():
                found.append(f"{locale}: {key} is empty")
            required = _holders(want) - OPTIONAL_PLACEHOLDERS.get(key, set())
            allowed = _holders(want) | EXTRA_PLACEHOLDERS.get(key, set())
            got = _holders(value)
            if not required <= got <= allowed:
                found.append(f"{locale}: {key} placeholders {sorted(got)} do not match {sorted(_holders(want))}")
            if locale == "en" and CJK.search(json.dumps(value, ensure_ascii=False)):
                found.append(f"{locale}: {key} contains Chinese, Japanese or Korean text")
    return found


def main() -> int:
    found = problems()
    if found:
        print("Interface catalog check failed:")
        for problem in found:
            print(f"  {problem}")
        return 1
    print(f"Interface catalog check passed: {', '.join(SUPPORTED_LOCALES)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
