"""Print Runner's version after checking that every place that states it agrees.

    python scripts/check_version.py                 pyproject.toml and __init__.py
    python scripts/check_version.py --tag 1.0.11    also the tag and CHANGELOG.md

pyproject.toml is the source. src/runner/__init__.py must match it. With
--tag, the tag must match too and CHANGELOG.md must have a "## [<tag>]"
section. Exits 1 with a message on the first disagreement.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _first(pattern: str, text: str, where: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        sys.exit(f"ERROR: no version found in {where}")
    return match.group(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", help="a release tag that must match the version")
    args = parser.parse_args()

    version = _first(r'^version\s*=\s*"([^"]+)"', _read("pyproject.toml"), "pyproject.toml")
    package = _first(
        r'^__version__\s*=\s*"([^"]+)"', _read("src/runner/__init__.py"), "src/runner/__init__.py"
    )
    if package != version:
        sys.exit(f"ERROR: pyproject.toml says {version} but src/runner/__init__.py says {package}")
    if args.tag is not None:
        if args.tag != version:
            sys.exit(f"ERROR: tag {args.tag} does not match pyproject.toml ({version})")
        if f"## [{version}]" not in _read("CHANGELOG.md"):
            sys.exit(f"ERROR: CHANGELOG.md has no '## [{version}]' section")
    print(version)


if __name__ == "__main__":
    main()
