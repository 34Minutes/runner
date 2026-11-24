"""scripts/bump_version.py: the version and changelog edits a release makes."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("bump_version", ROOT / "scripts" / "bump_version.py")
bump_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bump_version)

CHANGELOG = """# Changelog

Intro.

## [Unreleased]

### Added
- A new thing.

### Fixed
- A bug.

### Planned
- Icons.

## [1.1.2] - 2026-11-24

### Added
- Older.
"""


def _repo(tmp_path, changelog=CHANGELOG, pyproject="1.1.2", package="1.1.2"):
    (tmp_path / "src" / "runner").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "runner"\nversion = "{pyproject}"\n')
    (tmp_path / "src" / "runner" / "__init__.py").write_text(f'"""Runner."""\n\n__version__ = "{package}"\n')
    (tmp_path / "CHANGELOG.md").write_text(changelog)
    return tmp_path


def test_versions_count_up():
    assert bump_version.next_version("1.1.2", "patch") == "1.1.3"
    assert bump_version.next_version("1.1.2", "minor") == "1.2.0"
    assert bump_version.next_version("1.1.2", "major") == "2.0.0"


def test_a_bump_writes_both_versions_and_dates_the_unreleased_entries(tmp_path):
    root = _repo(tmp_path)
    assert bump_version.bump(root, "patch", "2026-11-30") == "1.1.3"
    assert 'version = "1.1.3"' in (root / "pyproject.toml").read_text()
    assert '__version__ = "1.1.3"' in (root / "src" / "runner" / "__init__.py").read_text()
    assert (root / "CHANGELOG.md").read_text() == """# Changelog

Intro.

## [Unreleased]

### Planned
- Icons.

## [1.1.3] - 2026-11-30

### Added
- A new thing.

### Fixed
- A bug.

## [1.1.2] - 2026-11-24

### Added
- Older.
"""


@pytest.mark.parametrize(
    "changelog, versions, problem",
    [
        (CHANGELOG.replace("### Added\n- A new thing.\n\n### Fixed\n- A bug.\n\n", ""), ("1.1.2", "1.1.2"),
         "no entries to release"),
        (CHANGELOG.replace("## [1.1.2]", "## [1.1.3]"), ("1.1.2", "1.1.2"), "already has a 1.1.3"),
        (CHANGELOG, ("1.1.2", "1.1.1"), "says 1.1.1"),
        (CHANGELOG.replace("## [Unreleased]", "## Next"), ("1.1.2", "1.1.2"), "has no .## .Unreleased.. section"),
    ],
)
def test_a_bump_that_cant_be_done_changes_nothing(tmp_path, changelog, versions, problem):
    root = _repo(tmp_path, changelog, *versions)
    before = {p: p.read_text() for p in root.rglob("*") if p.is_file()}
    with pytest.raises(bump_version.BumpError, match=problem):
        bump_version.bump(root, "patch", "2026-11-30")
    assert {p: p.read_text() for p in root.rglob("*") if p.is_file()} == before


def test_a_dry_run_writes_nothing(tmp_path, capsys):
    root = _repo(tmp_path)
    before = (root / "CHANGELOG.md").read_text()
    assert bump_version.bump(root, "minor", "2026-11-30", write=False) == "1.2.0"
    assert (root / "CHANGELOG.md").read_text() == before


def test_the_real_changelog_can_be_released():
    """The repo's own files are in a shape a bump can read (it writes nothing)."""
    try:
        bump_version.bump(ROOT, "patch", "2026-01-01", write=False)
    except bump_version.BumpError as problem:
        assert "no entries to release" in str(problem)  # fine right after a release
