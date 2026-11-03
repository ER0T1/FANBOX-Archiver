"""Static guard for the Asia/Taipei time contract (run by `npm run release:check`).

Python must never read or convert through the host timezone, and front-end code must
never let `Date` guess a zone or format without an explicit Asia/Taipei time zone.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "fanbox_archiver"

PYTHON_RULES = (
    (re.compile(r"datetime\.utcnow\("), "datetime.utcnow() returns a naive value"),
    (re.compile(r"datetime\.now\(\s*\)"), "datetime.now() without a timezone is naive"),
    (re.compile(r"\.astimezone\(\s*\)"), ".astimezone() without a zone uses the host timezone"),
    (re.compile(r"fromtimestamp\((?![^)]*tz=)[^)]*\)"), "fromtimestamp() without tz= is naive"),
)
FRONTEND_FILES = (
    *sorted((PACKAGE / "web_src").glob("*.ts")),
    *sorted((PACKAGE / "site_assets").glob("*.js")),
    *sorted((PACKAGE / "web_assets").glob("*.js")),
)


def main() -> int:
    problems: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for pattern, reason in PYTHON_RULES:
                if pattern.search(line):
                    problems.append(f"{path.relative_to(ROOT)}:{number}: {reason}")

    for path in FRONTEND_FILES:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        if "new Date(" in text and "explicitOffset" not in text:
            problems.append(f"{relative}: new Date() without the explicit-offset guard")
        if re.search(r"toLocale(?:Date|Time)String\(", text):
            problems.append(f"{relative}: toLocaleDateString/TimeString depends on the host timezone")
        for match in re.finditer(r"Intl\.DateTimeFormat\(", text):
            if "Asia/Taipei" not in text[match.end():match.end() + 200]:
                line = text.count("\n", 0, match.start()) + 1
                problems.append(f"{relative}:{line}: Intl.DateTimeFormat without timeZone Asia/Taipei")

    if problems:
        print("Time contract check failed:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("Time contract check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
