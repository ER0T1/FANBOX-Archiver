"""Static guard for the README / CHANGELOG contract (run by `npm run release:check`).

CHANGELOG.md is the only complete version history, newest first, starting at the
project version. README.md links to it and keeps exactly the newest three version
blocks, each identical to the matching CHANGELOG block.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README_KEEP = 3
VERSION_HEADING = re.compile(r"^## v(\d+)\.(\d+)\.(\d+)(-alpha)? (?:更新)?重點$")
PROJECT_VERSION = re.compile(r'__version__\s*=\s*"([^"]+)"')
CHANGELOG_LINK = "](CHANGELOG.md)"


def version_blocks(text: str) -> list[tuple[str, tuple[int, int, int, int], str]]:
    """Return (version, sort key, block text) for each `## vX.Y.Z 更新重點` block."""
    lines = text.splitlines()
    blocks = []
    for index, line in enumerate(lines):
        match = VERSION_HEADING.match(line)
        if not match:
            continue
        end = next((i for i in range(index + 1, len(lines)) if lines[i].startswith(("# ", "## "))), len(lines))
        major, minor, patch, alpha = match.groups()
        version = f"{major}.{minor}.{patch}{alpha or ''}"
        key = (int(major), int(minor), int(patch), 0 if alpha else 1)
        blocks.append((version, key, "\n".join(lines[index:end]).rstrip()))
    return blocks


def check(root: Path) -> list[str]:
    changelog_path = root / "CHANGELOG.md"
    if not changelog_path.is_file():
        return ["CHANGELOG.md is missing"]
    changelog = version_blocks(changelog_path.read_text(encoding="utf-8"))
    readme_text = (root / "README.md").read_text(encoding="utf-8")
    readme = version_blocks(readme_text)
    project = PROJECT_VERSION.search((root / "src" / "fanbox_archiver" / "__init__.py").read_text(encoding="utf-8"))

    problems: list[str] = []
    if not changelog:
        return ["CHANGELOG.md has no version blocks"]
    versions = [version for version, _, _ in changelog]
    duplicates = sorted({version for version in versions if versions.count(version) > 1})
    if duplicates:
        problems.append(f"CHANGELOG.md repeats versions: {', '.join(duplicates)}")
    for (newer, newer_key, _), (older, older_key, _) in zip(changelog, changelog[1:]):
        if newer_key <= older_key:
            problems.append(f"CHANGELOG.md is not newest first: v{newer} is followed by v{older}")
    if project and versions[0] != project.group(1):
        problems.append(f"CHANGELOG.md starts at v{versions[0]} but the project version is {project.group(1)}")

    if CHANGELOG_LINK not in readme_text:
        problems.append("README.md does not link to CHANGELOG.md")
    expected = changelog[:README_KEEP]
    if [version for version, _, _ in readme] != [version for version, _, _ in expected]:
        problems.append(
            f"README.md must keep exactly the newest {README_KEEP} versions "
            f"({', '.join('v' + v for v, _, _ in expected)}); found "
            f"{', '.join('v' + v for v, _, _ in readme) or 'none'}"
        )
    else:
        for (version, _, block), (_, _, logged) in zip(readme, expected):
            if block != logged:
                problems.append(f"README.md v{version} differs from its CHANGELOG.md block")
    return problems


def main() -> int:
    problems = check(ROOT)
    if problems:
        print("Changelog contract check failed:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("Changelog contract check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
