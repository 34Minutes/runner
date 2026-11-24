"""`runner project`: set a project up for Runner's scripts, and run them.

    runner project init          write .runner/project.toml with what it can detect
    runner project check         say what's ready and what's missing
    runner project launchers     make the project's launchers in Runner (via runner ctl)
    runner project guide         print the full guide (for people and LLMs)
    runner project push | merge | release | build    run a script

Every command works on the project the current folder is in (the nearest
folder with .runner/project.toml, else the git root), or on --project PATH.
The scripts are in runner/project_scripts; see runner/project.py for the file.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import sys
from pathlib import Path

from . import project as proj

EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2
SCRIPTS_DIR = Path(__file__).with_name("project_scripts")
APP_BINARY = Path("/Applications/Runner.app/Contents/MacOS/Runner")


def guide_text() -> str:
    return Path(__file__).with_name("project_guide.md").read_text(encoding="utf-8")


def self_command() -> tuple[str, list[str]]:
    """This very copy of `runner`: (program, words before 'project'). The scripts call it back."""
    if getattr(sys, "frozen", False):
        return sys.executable, []
    return sys.executable, ["-m", "runner"]


def launcher_command() -> tuple[str, list[str]]:
    """What a launcher starts: the installed app on a Mac, so it keeps working from any shell."""
    if not getattr(sys, "frozen", False) and sys.platform == "darwin" and APP_BINARY.exists():
        return str(APP_BINARY), []
    return self_command()


def log_dir(cfg: proj.ProjectConfig) -> Path:
    import platformdirs

    safe = re.sub(r"[^A-Za-z0-9._ -]", "_", cfg.name).strip() or "project"
    return Path(platformdirs.user_log_dir("Runner", appauthor=False)) / "scripts" / safe


def script_env(cfg: proj.ProjectConfig) -> dict[str, str]:
    program, prefix = self_command()
    env = dict(os.environ)
    env.update({
        "RUNNER_PROJECT_ROOT": str(cfg.root),
        "RUNNER_PROJECT_NAME": cfg.name,
        "RUNNER_MAIN_BRANCH": cfg.main_branch,
        "RUNNER_REMOTE": cfg.remote,
        "RUNNER_TAG_PATTERN": cfg.tag_pattern(),
        "RUNNER_LINT": cfg.lint,
        "RUNNER_TEST": cfg.test,
        "RUNNER_BUILD": cfg.build,
        "RUNNER_PUBLISHES": "1" if cfg.publishes else "0",
        "RUNNER_SELF": program,
        "RUNNER_SELF_MODULE": "1" if prefix else "",
        # The scripts call `runner project ...` back; it must find this project.
        "RUNNER_PROJECT": str(cfg.root),
    })
    env.setdefault("RUNNER_SCRIPTS_LOG_DIR", str(log_dir(cfg)))
    # A Qt path left in the shell makes a Python venv load a second Qt.
    for var in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        env.pop(var, None)
    return env


def run_script(cfg: proj.ProjectConfig, name: str, extra: list[str]) -> int:
    if name == "release" and not cfg.can_release:
        print("runner project: release needs a [version] file and a [changelog] file in "
              ".runner/project.toml.", file=sys.stderr)
        return EXIT_FAILED
    bash = "/bin/bash"
    if sys.platform == "win32" or not Path(bash).exists():
        print("runner project: the project scripts need bash (macOS or Linux).", file=sys.stderr)
        return EXIT_FAILED
    script = SCRIPTS_DIR / f"{name}.sh"
    # Replace this process with bash, so nothing of Runner stays running: a
    # build may replace Runner.app itself while the script carries on.
    sys.stdout.flush()
    sys.stderr.flush()
    os.execve(bash, [bash, str(script), *extra], script_env(cfg))
    return EXIT_OK  # not reached


# ---------------------------------------------------------------- launchers


def make_launchers(cfg: proj.ProjectConfig, source: str, container: str | None) -> list[str]:
    """Upsert a launcher per available script, and a container holding them. Returns lines to print."""
    from .ctl import NoAnswer, send

    program, prefix = launcher_command()
    names: list[str] = []
    lines: list[str] = []
    for script in proj.available_scripts(cfg):
        name = f"{cfg.name} {script.title()}"
        args = shlex.join([*prefix, "project", script, "--project", str(cfg.root)])
        request = {"op": "launcher.upsert", "source": source, "data": {
            "name": name, "command": program, "args": args,
            "working_dir": str(cfg.root), "show_in_main": False}}
        _send(send, NoAnswer, request)
        names.append(name)
        lines.append(f"Launcher: {name}  ->  runner project {script}")
    container = container or f"{cfg.name} Scripts"
    _send(send, NoAnswer, {"op": "container.upsert", "source": source,
                           "data": {"name": container, "launchers": names}})
    lines.append(f"Container group: {container} ({', '.join(names)})")
    if not cfg.can_release:
        lines.append("No Release launcher: set [version] and [changelog] in .runner/project.toml for one.")
    if not cfg.build:
        lines.append("No Build launcher: set commands.build in .runner/project.toml for one.")
    return lines


def _send(send, no_answer, request: dict) -> dict:
    try:
        reply, live = send(request)
    except no_answer as problem:
        raise proj.ProjectError(str(problem)) from None
    if not reply.get("ok"):
        raise proj.ProjectError(reply.get("error", "Runner refused that."))
    return reply


# ---------------------------------------------------------------- command line


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runner project",
        description="Set a project up for Runner's push, merge, release and build scripts, and run them.",
        epilog="New here? Run `runner project guide`.",
    )
    parser.add_argument("--project", metavar="PATH",
                        help="the project's folder (default: the one you're in, or $RUNNER_PROJECT)")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    sub.add_parser("guide", help="print the full guide: the project file, the scripts, setting up a project")
    init = sub.add_parser("init", help="write .runner/project.toml with what can be detected")
    init.add_argument("--force", action="store_true", help="replace an existing file")
    sub.add_parser("check", help="say what's ready and what's missing")
    launchers = sub.add_parser("launchers", help="make this project's launchers and container group in Runner")
    launchers.add_argument("--as", dest="source", default="cli", metavar="SOURCE",
                           help="the name to make them as, such as claude (default: cli)")
    launchers.add_argument("--container", metavar="NAME", help='its name (default: "<project> Scripts")')
    for name, text in (("push", "push the current branch (asks before publishing a release)"),
                       ("merge", "fast-forward the main branch to the current branch"),
                       ("release", "bump, date the changelog, commit, tag and (after asking) push"),
                       ("build", "run commands.build")):
        p = sub.add_parser(name, help=text)
        if name == "release":
            level = p.add_mutually_exclusive_group()
            for part in ("patch", "minor", "major"):
                level.add_argument(f"--{part}", dest="part", action="store_const", const=part,
                                   help=f"a {part} release, without asking")
            push = p.add_mutually_exclusive_group()
            push.add_argument("--publish", dest="publish", action="store_const", const=True,
                              help="push the release without asking")
            push.add_argument("--no-publish", dest="publish", action="store_const", const=False,
                              help="keep the release commit and tag here, without asking")
    sub.add_parser("version", help="print the project's version")
    bump = sub.add_parser("bump", help="write the next version and date the changelog (release does this)")
    bump.add_argument("part", choices=("patch", "minor", "major"))
    bump.add_argument("--dry-run", action="store_true", help="print the version it would make; write nothing")
    bump.add_argument("--print-files", action="store_true", help="print the files it changed")
    bump.add_argument("--date", help="the release date (default: today)")
    tag = sub.add_parser("tag", help="print the tag for a version")
    tag.add_argument("version")
    # --project works after the command too, as the launchers write it.
    for choice in sub.choices.values():
        choice.add_argument("--project", metavar="PATH", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    return parser


def script_args(args: argparse.Namespace) -> list[str]:
    extra = []
    if getattr(args, "part", None):
        extra.append(f"--{args.part}")
    if getattr(args, "publish", None) is not None:
        extra.append("--publish" if args.publish else "--no-publish")
    return extra


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_OK if exc.code == 0 else EXIT_USAGE
    if args.command == "guide":
        print(guide_text())
        return EXIT_OK
    try:
        start = Path(args.project or os.environ.get("RUNNER_PROJECT") or os.getcwd()).expanduser()
        if args.command == "init":
            root = proj.find_root(start) if not args.project else start.resolve()
            path = proj.init(root, force=args.force)
            print(f"Wrote {path}.")
            print("Next: read it and fill in anything left empty, then run `runner project check`.")
            return EXIT_OK
        cfg = proj.load(proj.find_root(start))
        if args.command == "check":
            return _print_check(cfg)
        if args.command == "launchers":
            for line in make_launchers(cfg, args.source, args.container):
                print(line)
            return EXIT_OK
        if args.command == "version":
            print(proj.current_version(cfg))
            return EXIT_OK
        if args.command == "tag":
            print(cfg.tag_for(args.version))
            return EXIT_OK
        if args.command == "bump":
            version = proj.bump(cfg, args.part, args.date, write=not args.dry_run)
            print("\n".join(proj.release_files(cfg)) if args.print_files else version)
            return EXIT_OK
        return run_script(cfg, args.command, script_args(args))
    except proj.ProjectError as problem:
        print(f"runner project: {problem}", file=sys.stderr)
        return EXIT_FAILED


def _print_check(cfg: proj.ProjectConfig) -> int:
    marks = {True: "ok  ", False: "FIX ", None: "note"}
    print(f"{cfg.name}  ({cfg.path})")
    results = proj.check(cfg)
    for item in results:
        print(f"  {marks[item.ok]}  {item.what}: {item.detail}")
    ready = proj.available_scripts(cfg)
    problems = [item for item in results if item.ok is False]
    print()
    if problems:
        print(f"{len(problems)} thing(s) to fix, marked FIX. Then run `runner project check` again.")
        return EXIT_FAILED
    print(f"Ready. Scripts: {', '.join(ready)}. Next: `runner project launchers --as <your name>`.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
