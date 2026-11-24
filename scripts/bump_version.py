"""Bump Runner's version and turn the changelog's Unreleased entries into a release.

    python scripts/bump_version.py patch          1.1.2 -> 1.1.3, and write it
    python scripts/bump_version.py minor          1.1.2 -> 1.2.0
    python scripts/bump_version.py major          1.1.2 -> 2.0.0
    python scripts/bump_version.py patch --dry-run   print the new version only

It writes the version into pyproject.toml and src/runner/__init__.py, and
moves every subsection under "## [Unreleased]" in CHANGELOG.md (Added,
Changed, Fixed, ...) into a new "## [<version>] - <today>" section below it.
"### Planned" stays under Unreleased. It prints the new version.

It refuses, changing nothing, when the two versions disagree, when
Unreleased has nothing to release, or when the changelog already has that
version.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEEP_UNRELEASED = ("Planned",)
_PYPROJECT_VERSION = re.compile(r'^(version\s*=\s*")([^"]+)(")', re.MULTILINE)
_PACKAGE_VERSION = re.compile(r'^(__version__\s*=\s*")([^"]+)(")', re.MULTILINE)


class BumpError(Exception):
    pass


def next_version(version: str, part: str) -> str:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if match is None:
        raise BumpError(f"{version!r} is not a version like 1.2.3.")
    major, minor, patch = (int(n) for n in match.groups())
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise BumpError(f"Bump patch, minor or major, not {part!r}.")


def _sections(lines: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Lines before the first ### heading, and each (heading, its lines)."""
    lead: list[str] = []
    subs: list[tuple[str, list[str]]] = []
    for line in lines:
        if line.startswith("### "):
            subs.append((line[4:].strip(), []))
        elif subs:
            subs[-1][1].append(line)
        else:
            lead.append(line)
    return lead, subs


def _trimmed(lines: list[str]) -> list[str]:
    while lines and not lines[0].strip():
        lines = lines[1:]
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    return lines


def release_changelog(text: str, version: str, day: str) -> str:
    """text with the Unreleased entries moved under a new version heading."""
    lines = text.split("\n")
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "## [Unreleased]")
    except StopIteration:
        raise BumpError('CHANGELOG.md has no "## [Unreleased]" section.') from None
    if any(line.startswith(f"## [{version}]") for line in lines):
        raise BumpError(f"CHANGELOG.md already has a {version} section.")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## [")), len(lines))
    lead, subs = _sections(lines[start + 1 : end])
    if any(line.strip() for line in lead):
        raise BumpError("Unreleased has text outside a ### subsection; tidy it first.")
    kept = [(name, body) for name, body in subs if name in KEEP_UNRELEASED]
    moving = [(name, _trimmed(body)) for name, body in subs if name not in KEEP_UNRELEASED]
    moving = [(name, body) for name, body in moving if any(line.strip() for line in body)]
    if not moving:
        raise BumpError("Unreleased has no entries to release. Add them to CHANGELOG.md first.")

    out = ["## [Unreleased]", ""]
    for name, body in kept:
        out += [f"### {name}", *_trimmed(body), ""]
    out += [f"## [{version}] - {day}", ""]
    for name, body in moving:
        out += [f"### {name}", *body, ""]
    return "\n".join(lines[:start] + out + lines[end:])


def _set(pattern: re.Pattern, text: str, version: str, where: str) -> tuple[str, str]:
    match = pattern.search(text)
    if match is None:
        raise BumpError(f"No version found in {where}.")
    return match.group(2), pattern.sub(lambda m: m.group(1) + version + m.group(3), text, count=1)


def bump(root: Path, part: str, day: str, *, write: bool = True) -> str:
    pyproject_path = root / "pyproject.toml"
    package_path = root / "src" / "runner" / "__init__.py"
    changelog_path = root / "CHANGELOG.md"
    pyproject = pyproject_path.read_text(encoding="utf-8")
    package = package_path.read_text(encoding="utf-8")
    current = _PYPROJECT_VERSION.search(pyproject)
    if current is None:
        raise BumpError("No version found in pyproject.toml.")
    version = next_version(current.group(2), part)
    old_pyproject, new_pyproject = _set(_PYPROJECT_VERSION, pyproject, version, "pyproject.toml")
    old_package, new_package = _set(_PACKAGE_VERSION, package, version, "src/runner/__init__.py")
    if old_package != old_pyproject:
        raise BumpError(f"pyproject.toml says {old_pyproject} but src/runner/__init__.py says {old_package}.")
    changelog = release_changelog(changelog_path.read_text(encoding="utf-8"), version, day)
    if write:
        pyproject_path.write_text(new_pyproject, encoding="utf-8")
        package_path.write_text(new_package, encoding="utf-8")
        changelog_path.write_text(changelog, encoding="utf-8")
    return version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("part", choices=("patch", "minor", "major"))
    parser.add_argument("--date", default=date.today().isoformat(), help="the release date (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="check and print the version; write nothing")
    args = parser.parse_args(argv)
    try:
        print(bump(ROOT, args.part, args.date, write=not args.dry_run))
    except BumpError as problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
