import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("check_changelog", ROOT / "scripts" / "check-changelog.py")
check_changelog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_changelog)


def block(version: str, note: str = "") -> str:
    return f"## v{version} 更新重點\n\n- {note or version} 的更新。\n"


def write_repo(root: Path, changelog: list[str], readme: list[str], project: str = "1.0.3-alpha", link: bool = True) -> Path:
    (root / "src" / "fanbox_archiver").mkdir(parents=True)
    (root / "src" / "fanbox_archiver" / "__init__.py").write_text(f'__version__ = "{project}"\n', encoding="utf-8")
    (root / "CHANGELOG.md").write_text("# 更新紀錄\n\n" + "\n".join(changelog), encoding="utf-8")
    note = "> 完整歷史請參閱 [CHANGELOG.md](CHANGELOG.md)。\n\n" if link else ""
    (root / "README.md").write_text("# App\n\n" + note + "\n".join(readme) + "\n## 安裝\n\n說明\n", encoding="utf-8")
    return root


VERSIONS = ["1.0.3-alpha", "1.0.2-alpha", "1.0.1-alpha", "1.0.0-alpha"]


def test_repository_passes_contract():
    assert check_changelog.check(ROOT) == []


def test_newest_three_in_readme_pass(tmp_path):
    repo = write_repo(tmp_path, [block(v) for v in VERSIONS], [block(v) for v in VERSIONS[:3]])
    assert check_changelog.check(repo) == []


@pytest.mark.parametrize(
    ("changelog", "readme", "kwargs", "expected"),
    [
        (VERSIONS, VERSIONS, {}, "exactly the newest 3"),
        (VERSIONS[1:], VERSIONS[:3], {}, "exactly the newest 3"),
        (["1.0.3-alpha", "1.0.1-alpha", "1.0.2-alpha", "1.0.0-alpha"], ["1.0.3-alpha", "1.0.1-alpha", "1.0.2-alpha"], {}, "not newest first"),
        (["1.0.3-alpha", "1.0.3-alpha", "1.0.2-alpha"], ["1.0.3-alpha", "1.0.3-alpha", "1.0.2-alpha"], {}, "repeats versions"),
        (VERSIONS, VERSIONS[:3], {"project": "1.0.4-alpha"}, "project version is 1.0.4-alpha"),
        (VERSIONS, VERSIONS[:3], {"link": False}, "does not link"),
    ],
)
def test_contract_violations_are_reported(tmp_path, changelog, readme, kwargs, expected):
    repo = write_repo(tmp_path, [block(v) for v in changelog], [block(v) for v in readme], **kwargs)
    assert any(expected in problem for problem in check_changelog.check(repo))


def test_readme_block_must_match_changelog(tmp_path):
    readme = [block("1.0.3-alpha", "改寫過"), *[block(v) for v in VERSIONS[1:3]]]
    repo = write_repo(tmp_path, [block(v) for v in VERSIONS], readme)
    assert check_changelog.check(repo) == ["README.md v1.0.3-alpha differs from its CHANGELOG.md block"]


def test_missing_changelog_is_reported(tmp_path):
    repo = write_repo(tmp_path, [], [])
    (repo / "CHANGELOG.md").unlink()
    assert check_changelog.check(repo) == ["CHANGELOG.md is missing"]
