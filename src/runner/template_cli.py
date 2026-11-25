"""`runner template`: script templates to copy into a project and make your own.

Runner doesn't run them or read them. A copied template is the project's own
script: edit its settings, commit it, and make a launcher for it with
`runner ctl`. The templates are in runner/templates.
"""

from __future__ import annotations

import argparse
import os
import shlex
import stat
import sys
from pathlib import Path

TEMPLATES_DIR = Path(__file__).with_name("templates")
EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2


def names() -> list[str]:
    return sorted(p.stem for p in TEMPLATES_DIR.glob("*.sh"))


def path_of(name: str) -> Path:
    name = name.removesuffix(".sh")
    if name not in names():
        raise LookupError(f"There is no {name!r} template. `runner template list` shows them.")
    return TEMPLATES_DIR / f"{name}.sh"


def summary(name: str) -> str:
    """The template's first comment line after the #! line, without the name."""
    for line in path_of(name).read_text(encoding="utf-8").splitlines()[1:]:
        if line.startswith("# "):
            return line[2:].split(": ", 1)[-1]
    return ""


def copy(name: str, folder: Path, *, force: bool = False) -> Path:
    source = path_of(name)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / source.name
    if target.exists() and not force:
        raise FileExistsError(f"{target} already exists. Use --force to replace it.")
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runner template",
        description="Script templates (build, merge, push, release, test-once) to copy into a project.",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    sub.add_parser("list", help="the templates, with what each does")
    show = sub.add_parser("show", help="print a template")
    show.add_argument("name")
    cp = sub.add_parser("copy", help="copy templates into a folder (default: ./scripts), ready to edit")
    cp.add_argument("names", nargs="+", metavar="NAME")
    cp.add_argument("--to", default="scripts", metavar="FOLDER", help="where to put them (default: scripts)")
    cp.add_argument("--force", action="store_true", help="replace files that are already there")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return EXIT_OK if exc.code == 0 else EXIT_USAGE
    try:
        if args.command == "list":
            width = max(map(len, names()))
            for name in names():
                print(f"{name:<{width}}  {summary(name)}")
            return EXIT_OK
        if args.command == "show":
            print(path_of(args.name).read_text(encoding="utf-8"), end="")
            return EXIT_OK
        folder = Path(args.to).expanduser().resolve()
        made = [copy(name, folder, force=args.force) for name in args.names]
    except (LookupError, OSError) as problem:
        print(f"runner template: {problem}", file=sys.stderr)
        return EXIT_FAILED
    for path in made:
        print(f"Copied {path}")
    print("\nNext: edit the settings at the top of each, then make a launcher for it, for example:")
    first = made[0]
    print("  runner ctl --as <you> launcher upsert --name "
          f"{shlex.quote(first.parent.parent.name + ' ' + first.stem.replace('-', ' ').title())} "
          f"--command {shlex.quote(str(first))} --cwd {shlex.quote(str(first.parent.parent))}")
    if os.name == "nt":
        print("These scripts need bash: they run on macOS and Linux.")
    return EXIT_OK
