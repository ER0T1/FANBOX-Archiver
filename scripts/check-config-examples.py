from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fanbox_archiver.config_contract import check_registered_examples  # noqa: E402


def main() -> int:
    reports = check_registered_examples(PROJECT_ROOT)
    failures = [report for report in reports if not report.passed]
    if failures:
        print("Configuration example contract failed:", file=sys.stderr)
        for report in failures:
            print("\n".join(report.lines()), file=sys.stderr)
        return 1
    names = ", ".join(str(report.relative_path) for report in reports)
    print(f"Configuration example contract passed: {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
