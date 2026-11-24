"""Runner's project scripts: what a project tells them, in .runner/project.toml.

A project that wants Runner's push, merge, release and build launchers keeps
a small file, .runner/project.toml, at its root. `runner project init` writes
one with what it can detect; `runner project check` says what is missing.
The scripts themselves (runner/project_scripts/*.sh) read the values this
module hands them, so the same scripts work in any project.

This module is free of Qt and of the UI.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

CONFIG_DIR = ".runner"
CONFIG_NAME = "project.toml"
SCRIPTS = ("build", "merge", "push", "release")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
# A version stated in a file: version = "1.2.3", __version__ = '1.2.3',
# "version": "1.2.3", or a file that holds nothing but the version.
_STATED = re.compile(
    r"""(?mi)^(\s*["']?(?:__version__|version)["']?\s*[:=]\s*["'])(\d+\.\d+\.\d+)(["'])"""
)


class ProjectError(Exception):
    """Something about the project or its file, in words for whoever runs it."""


@dataclass
class ProjectConfig:
    root: Path
    name: str
    main_branch: str = "main"
    remote: str = "origin"
    version_file: str = ""
    version_also: list[str] = field(default_factory=list)
    tag: str = "{version}"
    changelog: str = ""
    keep_unreleased: list[str] = field(default_factory=lambda: ["Planned"])
    lint: str = ""
    test: str = ""
    build: str = ""
    publishes: bool = False

    @property
    def path(self) -> Path:
        return self.root / CONFIG_DIR / CONFIG_NAME

    @property
    def can_release(self) -> bool:
        return bool(self.version_file and self.changelog)

    def tag_for(self, version: str) -> str:
        return self.tag.replace("{version}", version)

    def tag_pattern(self) -> str:
        """An extended regex matching this project's release tags."""
        before, _, after = self.tag.partition("{version}")
        return "^" + re.escape(before) + r"[0-9]+\.[0-9]+\.[0-9]+" + re.escape(after) + "$"


# ---------------------------------------------------------------- finding and loading


def find_root(start: Path) -> Path:
    """The project a command is about: the nearest folder with .runner/, else the git root."""
    start = start.resolve()
    for folder in (start, *start.parents):
        if (folder / CONFIG_DIR / CONFIG_NAME).is_file():
            return folder
    top = _git(start, "rev-parse", "--show-toplevel")
    if top:
        return Path(top)
    raise ProjectError(f"{start} is not inside a git repository. Pass --project with the project's folder.")


def load(root: Path) -> ProjectConfig:
    path = root / CONFIG_DIR / CONFIG_NAME
    if not path.is_file():
        raise ProjectError(f"{root} has no {CONFIG_DIR}/{CONFIG_NAME}. Run `runner project init` there first.")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ProjectError(f"{path} can't be read: {exc}") from None

    def section(name: str) -> dict:
        value = data.get(name, {})
        if not isinstance(value, dict):
            raise ProjectError(f"[{name}] in {path} must be a table.")
        return value

    def text(table: dict, key: str, default: str, where: str) -> str:
        value = table.get(key, default)
        if not isinstance(value, str):
            raise ProjectError(f"{where}.{key} in {path} must be text.")
        return value.strip()

    def texts(table: dict, key: str, default: list[str], where: str) -> list[str]:
        value = table.get(key, default)
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ProjectError(f"{where}.{key} in {path} must be a list of text.")
        return [v.strip() for v in value if v.strip()]

    project, version, changelog = section("project"), section("version"), section("changelog")
    commands, release = section("commands"), section("release")
    cfg = ProjectConfig(
        root=root,
        name=text(project, "name", root.name, "project") or root.name,
        main_branch=text(project, "main_branch", "main", "project") or "main",
        remote=text(project, "remote", "origin", "project") or "origin",
        version_file=text(version, "file", "", "version"),
        version_also=texts(version, "also", [], "version"),
        tag=text(version, "tag", "{version}", "version") or "{version}",
        changelog=text(changelog, "file", "", "changelog"),
        keep_unreleased=texts(changelog, "keep_unreleased", ["Planned"], "changelog"),
        lint=text(commands, "lint", "", "commands"),
        test=text(commands, "test", "", "commands"),
        build=text(commands, "build", "", "commands"),
        publishes=bool(release.get("publishes", False)),
    )
    if "{version}" not in cfg.tag:
        raise ProjectError(f'version.tag in {path} must contain {{version}}, like "v{{version}}".')
    return cfg


# ---------------------------------------------------------------- versions


def read_version(root: Path, relative: str) -> str:
    path = root / relative
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProjectError(f"Can't read {relative}: {exc.strerror or exc}.") from None
    if VERSION_RE.match(text.strip()):
        return text.strip()
    match = _STATED.search(text)
    if match is None:
        raise ProjectError(f'{relative} has no version like version = "1.2.3".')
    return match.group(2)


def _write_version(root: Path, relative: str, version: str) -> str:
    """The file's new text with version in place of the one it states."""
    text = (root / relative).read_text(encoding="utf-8")
    if VERSION_RE.match(text.strip()):
        return text.replace(text.strip(), version, 1)
    return _STATED.sub(lambda m: m.group(1) + version + m.group(3), text, count=1)


def current_version(cfg: ProjectConfig) -> str:
    if not cfg.version_file:
        raise ProjectError("This project has no [version] file in .runner/project.toml.")
    version = read_version(cfg.root, cfg.version_file)
    for other in cfg.version_also:
        stated = read_version(cfg.root, other)
        if stated != version:
            raise ProjectError(f"{cfg.version_file} says {version} but {other} says {stated}.")
    return version


def next_version(version: str, part: str) -> str:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if match is None:
        raise ProjectError(f"{version!r} is not a version like 1.2.3.")
    major, minor, patch = (int(n) for n in match.groups())
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ProjectError(f"Bump patch, minor or major, not {part!r}.")


# ---------------------------------------------------------------- the changelog


def _sections(lines: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
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


def unreleased_entries(text: str, keep: list[str]) -> int:
    """How many entries (lines starting "- ") Unreleased has to release."""
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if line.strip() == "## [Unreleased]"), None)
    if start is None:
        return -1
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## [")), len(lines))
    _, subs = _sections(lines[start + 1 : end])
    return sum(
        1 for name, body in subs if name not in keep for line in body if line.lstrip().startswith(("- ", "* "))
    )


def release_changelog(text: str, version: str, day: str, keep: list[str]) -> str:
    """text with the Unreleased entries moved under "## [version] - day"."""
    lines = text.split("\n")
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "## [Unreleased]")
    except StopIteration:
        raise ProjectError('The changelog has no "## [Unreleased]" section.') from None
    if any(line.startswith(f"## [{version}]") for line in lines):
        raise ProjectError(f"The changelog already has a {version} section.")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## [")), len(lines))
    lead, subs = _sections(lines[start + 1 : end])
    if any(line.strip() for line in lead):
        raise ProjectError("Unreleased has text outside a ### subsection (like ### Added). Tidy it first.")
    kept = [(name, body) for name, body in subs if name in keep]
    moving = [(name, _trimmed(body)) for name, body in subs if name not in keep]
    moving = [(name, body) for name, body in moving if any(line.strip() for line in body)]
    if not moving:
        raise ProjectError("Unreleased has no entries to release. Add them to the changelog first.")
    out = ["## [Unreleased]", ""]
    for name, body in kept:
        out += [f"### {name}", *_trimmed(body), ""]
    out += [f"## [{version}] - {day}", ""]
    for name, body in moving:
        out += [f"### {name}", *body, ""]
    return "\n".join(lines[:start] + out + lines[end:])


def bump(cfg: ProjectConfig, part: str, day: str | None = None, *, write: bool = True) -> str:
    """Write the next version everywhere it is stated and date the changelog. Returns it."""
    if not cfg.changelog:
        raise ProjectError("This project has no [changelog] file in .runner/project.toml.")
    version = next_version(current_version(cfg), part)
    files = {rel: _write_version(cfg.root, rel, version) for rel in [cfg.version_file, *cfg.version_also]}
    try:
        changelog = (cfg.root / cfg.changelog).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProjectError(f"Can't read {cfg.changelog}: {exc.strerror or exc}.") from None
    files[cfg.changelog] = release_changelog(changelog, version, day or date.today().isoformat(), cfg.keep_unreleased)
    if write:
        for rel, text in files.items():
            (cfg.root / rel).write_text(text, encoding="utf-8")
    return version


def release_files(cfg: ProjectConfig) -> list[str]:
    return [cfg.version_file, *cfg.version_also, cfg.changelog]


# ---------------------------------------------------------------- init and check


def _git(root: Path, *args: str) -> str:
    try:
        done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def _toml_text(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # a JSON string is a valid TOML basic string


def detect(root: Path) -> dict:
    """Best guesses for a new project file. Anything unsure is left empty."""
    guess: dict = {"name": root.name, "main_branch": "main", "remote": "origin", "version_file": "",
                   "version_also": [], "changelog": "", "lint": "", "test": "", "build": ""}
    remotes = _git(root, "remote").split()
    if remotes:
        guess["remote"] = "origin" if "origin" in remotes else remotes[0]
    head = _git(root, "symbolic-ref", "--short", f"refs/remotes/{guess['remote']}/HEAD")
    if head:
        guess["main_branch"] = head.split("/", 1)[-1]
    elif _git(root, "rev-parse", "--verify", "-q", "refs/heads/master") and not _git(
        root, "rev-parse", "--verify", "-q", "refs/heads/main"
    ):
        guess["main_branch"] = "master"
    for candidate in ("pyproject.toml", "package.json", "Cargo.toml", "VERSION", "version.txt"):
        if (root / candidate).is_file():
            try:
                read_version(root, candidate)
            except ProjectError:
                continue
            guess["version_file"] = candidate
            break
    if guess["version_file"] == "pyproject.toml":
        for init in sorted(root.glob("src/*/__init__.py")) + sorted(root.glob("*/__init__.py")):
            try:
                read_version(root, str(init.relative_to(root)))
            except ProjectError:
                continue
            guess["version_also"].append(str(init.relative_to(root)))
    for candidate in ("CHANGELOG.md", "Changelog.md", "CHANGES.md", "HISTORY.md"):
        if (root / candidate).is_file():
            guess["changelog"] = candidate
            break
    venv_python = ".venv/bin/python"
    if (root / "pyproject.toml").is_file():
        python = venv_python if (root / venv_python).exists() else "python3"
        if (root / "tests").is_dir():
            guess["test"] = f"{python} -m pytest -q"
        if (root / venv_python).exists() and (root / ".venv/bin/ruff").exists():
            guess["lint"] = f"{python} -m ruff check ."
    if (root / "package.json").is_file():
        try:
            scripts = json.loads((root / "package.json").read_text(encoding="utf-8")).get("scripts", {})
        except (OSError, ValueError, AttributeError):
            scripts = {}
        if isinstance(scripts, dict):
            if "test" in scripts:
                guess["test"] = "npm test"
            if "lint" in scripts:
                guess["lint"] = "npm run lint"
            if "build" in scripts:
                guess["build"] = "npm run build"
    if (root / "Cargo.toml").is_file():
        guess["test"] = guess["test"] or "cargo test"
        guess["build"] = guess["build"] or "cargo build --release"
    return guess


def template(guess: dict) -> str:
    also = ", ".join(_toml_text(v) for v in guess["version_also"])
    return f"""# How Runner's project scripts (build, merge, push, release) work in this project.
# Check it with `runner project check`. `runner project guide` explains every line.

[project]
# Shown in notifications and in the launchers' names.
name = {_toml_text(guess["name"])}
# Merge fast-forwards into this branch. Releases are made from it.
main_branch = {_toml_text(guess["main_branch"])}
# Where push and release send commits and tags.
remote = {_toml_text(guess["remote"])}

[version]
# The file that states the version: version = "1.2.3" (pyproject.toml, Cargo.toml),
# "version": "1.2.3" (package.json), or a VERSION file holding only 1.2.3.
# Empty if the project has no version; Release is then unavailable.
file = {_toml_text(guess["version_file"])}
# Other files that state the same version. Release updates them too.
also = [{also}]
# How release tags are written, for example "v{{version}}".
tag = "{{version}}"

[changelog]
# Keep a Changelog format (https://keepachangelog.com): a "## [Unreleased]" section
# with "### Added", "### Changed", "### Fixed" subsections. Release moves them under
# a new "## [x.y.z] - date" section. Empty if there is none; Release is then unavailable.
file = {_toml_text(guess["changelog"])}
# Subsections that stay under Unreleased at a release.
keep_unreleased = ["Planned"]

[commands]
# Shell commands, run from the project's folder. Leave one empty to skip it.
# Release runs lint, then test; a failure stops the release before anything changes.
lint = {_toml_text(guess["lint"])}
test = {_toml_text(guess["test"])}
# The Build launcher runs this.
build = {_toml_text(guess["build"])}

[release]
# true if pushing a release tag publishes something public (for example a CI release).
# Release and Push then ask before pushing a new release tag.
publishes = false
"""


def init(root: Path, *, force: bool = False) -> Path:
    path = root / CONFIG_DIR / CONFIG_NAME
    if path.exists() and not force:
        raise ProjectError(f"{path} already exists. Edit it, or pass --force to start over.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template(detect(root)), encoding="utf-8")
    return path


@dataclass
class Check:
    ok: bool | None  # None: fine but worth knowing
    what: str
    detail: str = ""


def _command_found(root: Path, command: str) -> bool:
    first = command.split()[0] if command.split() else ""
    if not first:
        return True
    if "/" in first:
        return (root / first).exists() or Path(first).expanduser().exists()
    return shutil.which(first) is not None


def check(cfg: ProjectConfig) -> list[Check]:
    root = cfg.root
    out: list[Check] = []
    if not _git(root, "rev-parse", "--git-dir"):
        return [Check(False, "Git repository", f"{root} is not a git repository. Run `git init` there.")]
    out.append(Check(True, "Git repository", str(root)))
    if _git(root, "rev-parse", "--verify", "-q", f"refs/heads/{cfg.main_branch}"):
        out.append(Check(True, "Main branch", cfg.main_branch))
    else:
        out.append(Check(False, "Main branch", f"There is no branch {cfg.main_branch!r}. Fix project.main_branch."))
    if cfg.remote in _git(root, "remote").split():
        out.append(Check(True, "Remote", f"{cfg.remote} ({_git(root, 'remote', 'get-url', cfg.remote)})"))
    else:
        out.append(Check(False, "Remote", f"No remote {cfg.remote!r}. Push and release need one: "
                                         f"git remote add {cfg.remote} <url>, or fix project.remote."))
    if cfg.version_file:
        try:
            out.append(Check(True, "Version", f"{current_version(cfg)} in {cfg.version_file}"
                             + (f" (and {', '.join(cfg.version_also)})" if cfg.version_also else "")))
        except ProjectError as problem:
            out.append(Check(False, "Version", str(problem)))
    else:
        out.append(Check(None, "Version", "None set, so Release is unavailable."))
    if cfg.changelog:
        try:
            text = (root / cfg.changelog).read_text(encoding="utf-8")
        except OSError:
            out.append(Check(False, "Changelog", f"{cfg.changelog} doesn't exist. Create it, or clear changelog.file."))
        else:
            count = unreleased_entries(text, cfg.keep_unreleased)
            if count < 0:
                out.append(Check(False, "Changelog", f'{cfg.changelog} has no "## [Unreleased]" section. Add one.'))
            elif count == 0:
                out.append(Check(None, "Changelog", f"{cfg.changelog} is ready; Unreleased has no entries yet, "
                                                   "so there is nothing to release."))
            else:
                out.append(Check(True, "Changelog", f"{cfg.changelog}: {count} entr{'y' if count == 1 else 'ies'} "
                                                   "under Unreleased"))
    else:
        out.append(Check(None, "Changelog", "None set, so Release is unavailable."))
    for name in ("lint", "test", "build"):
        command = getattr(cfg, name)
        if not command:
            out.append(Check(None, f"{name.title()} command", "None: skipped."
                             + (" The Build launcher needs one." if name == "build" else "")))
        elif _command_found(root, command):
            out.append(Check(True, f"{name.title()} command", command))
        else:
            out.append(Check(False, f"{name.title()} command", f"{command.split()[0]} wasn't found. Fix commands.{name}."))
    if cfg.publishes:
        out.append(Check(None, "Publishing", f"Pushing a {cfg.tag_for('x.y.z')} tag publishes a release; "
                                            "Release and Push ask before doing it."))
    return out


def available_scripts(cfg: ProjectConfig) -> list[str]:
    scripts = ["merge", "push"]
    if cfg.can_release:
        scripts.append("release")
    if cfg.build:
        scripts.insert(0, "build")
    return scripts
