"""Static guard for the display-timezone contract (run by `npm run release:check`).

Every user-visible time goes through the one configured display timezone and is
24-hour HH:MM. Python must not read or convert through the host timezone or bypass
the shared setting; front-end code must not let `Date` guess a zone, hard-code a
zone in a formatter, format without 24-hour time, or use a locale-dependent native
time input.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "fanbox_archiver"
SHARED_MODULE = PACKAGE / "timestamps.py"

PYTHON_RULES = (
    (re.compile(r"datetime\.utcnow\("), "datetime.utcnow() returns a naive value"),
    (re.compile(r"datetime\.now\(\s*\)"), "datetime.now() without a timezone is naive"),
    (re.compile(r"\.astimezone\(\s*\)"), ".astimezone() without a zone uses the host timezone"),
    (re.compile(r"fromtimestamp\((?![^)]*tz=)[^)]*\)"), "fromtimestamp() without tz= is naive"),
)
BYPASS = re.compile(r"\bTAIPEI\b")
FRONTEND_FILES = (
    *sorted((PACKAGE / "web_src").glob("*.ts")),
    *sorted((PACKAGE / "site_assets").glob("*.js")),
    *sorted((PACKAGE / "web_assets").glob("*.js")),
)
MARKUP_FILES = (*FRONTEND_FILES, *sorted((PACKAGE / "web_assets").glob("*.html")))
NATIVE_TIME_INPUT = re.compile(r"""type\s*[:=]\s*["']time["']""")
ZONE_OPTION = re.compile(r"timeZone\s*:\s*([^,}\s]+)")
H23 = re.compile(r"""hourCycle\s*:\s*["']h23["']""")


def main() -> int:
    problems: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for pattern, reason in PYTHON_RULES:
                if pattern.search(line):
                    problems.append(f"{path.relative_to(ROOT)}:{number}: {reason}")
            if path != SHARED_MODULE and BYPASS.search(line):
                problems.append(f"{path.relative_to(ROOT)}:{number}: use the shared display timezone instead of TAIPEI")

    for path in MARKUP_FILES:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if NATIVE_TIME_INPUT.search(line):
                problems.append(
                    f"{path.relative_to(ROOT)}:{number}: native time input follows the OS locale; use 24-hour pickers"
                )

    for path in FRONTEND_FILES:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        if "new Date(" in text and "explicitOffset" not in text:
            problems.append(f"{relative}: new Date() without the explicit-offset guard")
        if re.search(r"toLocale(?:Date|Time)String\(", text):
            problems.append(f"{relative}: toLocaleDateString/TimeString depends on the host timezone")
        for match in re.finditer(r"Intl\.DateTimeFormat\(", text):
            options = text[match.end():match.end() + 250]
            line = text.count("\n", 0, match.start()) + 1
            zone = ZONE_OPTION.search(options)
            if zone is None:
                problems.append(f"{relative}:{line}: Intl.DateTimeFormat without the shared display timeZone")
            elif zone.group(1)[:1] in {"'", '"', "`"}:
                problems.append(f"{relative}:{line}: Intl.DateTimeFormat hard-codes a time zone")
            if re.search(r"\bhour\s*:", options) and not H23.search(options):
                problems.append(f"{relative}:{line}: Intl.DateTimeFormat must use 24-hour hourCycle h23")

    if problems:
        print("Time contract check failed:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("Time contract check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
