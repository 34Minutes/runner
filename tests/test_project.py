"""`runner project`: the project file, the version bump, the scripts, and Help."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from runner import project as proj
from runner import project_cli

ROOT = Path(__file__).resolve().parent.parent
needs_bash = pytest.mark.skipif(sys.platform == "win32", reason="the project scripts need bash")

CHANGELOG = """# Changelog

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

PROJECT_FILE = """[project]
name = "Demo"

[version]
file = "pyproject.toml"
also = ["demo/__init__.py"]
tag = "v{version}"

[changelog]
file = "CHANGELOG.md"

[commands]
lint = "true"
test = "true"
build = "echo built > built.txt"
"""


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def _project(tmp_path, *, project_file=PROJECT_FILE, changelog=CHANGELOG, package="1.1.2", remote=True):
    """A git project with a remote, ready for the scripts."""
    root = tmp_path / "demo"
    (root / "demo").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "1.1.2"\n')
    (root / "demo" / "__init__.py").write_text(f'__version__ = "{package}"\n')
    (root / "CHANGELOG.md").write_text(changelog)
    if project_file is not None:
        (root / ".runner").mkdir()
        (root / ".runner" / "project.toml").write_text(project_file)
    _git(tmp_path, "init", "-q", "-b", "main", str(root))
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "start")
    if remote:
        _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(tmp_path / "remote.git"))
        _git(root, "remote", "add", "origin", str(tmp_path / "remote.git"))
        _git(root, "push", "-q", "origin", "main")
    return root


def _run(root, *args, logs=None):
    """`runner project ...` as a launcher would start it, quietly."""
    env = dict(os.environ, RUNNER_SCRIPTS_QUIET="1", PYTHONPATH=str(ROOT / "src"))
    env["RUNNER_SCRIPTS_LOG_DIR"] = str(logs or root.parent / "logs")
    done = subprocess.run([sys.executable, "-m", "runner", "project", *args], cwd=root, env=env,
                          capture_output=True, text=True, timeout=60)
    return done.returncode, done.stdout + done.stderr


# ------------------------------------------------------------------ the project file


def test_the_project_file_is_read_with_defaults(tmp_path):
    root = _project(tmp_path, remote=False)
    cfg = proj.load(root)
    assert (cfg.name, cfg.main_branch, cfg.remote, cfg.tag) == ("Demo", "main", "origin", "v{version}")
    assert cfg.tag_for("1.2.0") == "v1.2.0" and cfg.publishes is False
    assert cfg.keep_unreleased == ["Planned"]
    assert proj.available_scripts(cfg) == ["build", "merge", "push", "release"]
    assert proj.find_root(root / "demo") == root


def test_a_bad_project_file_is_explained(tmp_path):
    root = _project(tmp_path, project_file='[version]\ntag = "release"\n', remote=False)
    with pytest.raises(proj.ProjectError, match="must contain"):
        proj.load(root)
    (root / ".runner" / "project.toml").write_text("[project\n")
    with pytest.raises(proj.ProjectError, match="can't be read"):
        proj.load(root)


def test_init_detects_what_it_can_and_check_says_what_is_missing(tmp_path):
    root = _project(tmp_path, project_file=None, remote=False)
    (root / "tests").mkdir()
    path = proj.init(root)
    text = path.read_text()
    assert 'file = "pyproject.toml"' in text and 'also = ["demo/__init__.py"]' in text
    assert 'file = "CHANGELOG.md"' in text and "-m pytest -q" in text
    with pytest.raises(proj.ProjectError, match="already exists"):
        proj.init(root)
    results = {c.what: c for c in proj.check(proj.load(root))}
    assert results["Version"].ok and "1.1.2" in results["Version"].detail
    assert results["Changelog"].ok and "2 entries" in results["Changelog"].detail
    assert results["Remote"].ok is False  # no remote yet
    assert results["Build command"].ok is None


def test_versions_in_every_common_format_are_read_and_written(tmp_path):
    files = {
        "pyproject.toml": '[project]\nversion = "1.2.3"\n',
        "package.json": '{\n  "name": "x",\n  "version": "1.2.3",\n  "dependencies": {"a": "1.0.0"}\n}\n',
        "Cargo.toml": '[package]\nversion = "1.2.3"\n\n[dependencies]\nserde = { version = "1.0.1" }\n',
        "mod.py": '__version__ = "1.2.3"\n',
        "VERSION": "1.2.3\n",
    }
    for name, text in files.items():
        (tmp_path / name).write_text(text)
        assert proj.read_version(tmp_path, name) == "1.2.3", name
        written = proj._write_version(tmp_path, name, "1.3.0")
        assert written.count("1.3.0") == 1 and "1.2.3" not in written, name
    assert '"a": "1.0.0"' in proj._write_version(tmp_path, "package.json", "2.0.0")


# ------------------------------------------------------------------ the bump


def test_a_bump_writes_every_version_and_dates_the_unreleased_entries(tmp_path):
    root = _project(tmp_path, remote=False)
    cfg = proj.load(root)
    assert proj.bump(cfg, "minor", "2026-11-30") == "1.2.0"
    assert 'version = "1.2.0"' in (root / "pyproject.toml").read_text()
    assert '__version__ = "1.2.0"' in (root / "demo" / "__init__.py").read_text()
    assert (root / "CHANGELOG.md").read_text() == """# Changelog

## [Unreleased]

### Planned
- Icons.

## [1.2.0] - 2026-11-30

### Added
- A new thing.

### Fixed
- A bug.

## [1.1.2] - 2026-11-24

### Added
- Older.
"""


@pytest.mark.parametrize("changelog, package, problem", [
    (CHANGELOG.replace("### Added\n- A new thing.\n\n### Fixed\n- A bug.\n\n", ""), "1.1.2", "no entries"),
    (CHANGELOG.replace("## [1.1.2]", "## [1.1.3]"), "1.1.2", "already has a 1.1.3"),
    (CHANGELOG, "1.1.1", "says 1.1.1"),
    (CHANGELOG.replace("## [Unreleased]", "## Next"), "1.1.2", "Unreleased"),
])
def test_a_bump_that_cant_be_done_changes_nothing(tmp_path, changelog, package, problem):
    root = _project(tmp_path, changelog=changelog, package=package, remote=False)
    before = {p: p.read_text() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}
    with pytest.raises(proj.ProjectError, match=problem):
        proj.bump(proj.load(root), "patch", "2026-11-30")
    assert {p: p.read_text() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts} == before


def test_runners_own_project_file_is_ready():
    cfg = proj.load(ROOT)
    assert cfg.name == "Runner" and cfg.publishes and cfg.build.startswith("./scripts/build-mac.sh")
    assert not [c for c in proj.check(cfg) if c.ok is False and c.what != "Remote"]


# ------------------------------------------------------------------ the scripts, for real


@needs_bash
def test_merge_fast_forwards_and_stops_for_anything_else(tmp_path):
    root = _project(tmp_path)
    code, out = _run(root, "merge")
    assert code == 1 and "You're on main" in out
    _git(root, "checkout", "-qb", "feature")
    (root / "f.txt").write_text("f")
    _git(root, "add", "f.txt")
    _git(root, "commit", "-qm", "f")
    (root / "CHANGELOG.md").write_text(CHANGELOG + "dirty")
    code, out = _run(root, "merge")
    assert code == 1 and "uncommitted changes" in out
    _git(root, "checkout", "-q", "CHANGELOG.md")
    code, out = _run(root, "merge")
    assert code == 0 and "Merged feature into main (1 commit(s))" in out
    assert _git(root, "branch", "--show-current") == "main"
    log = (tmp_path / "logs" / "merge.log").read_text()
    assert "Merged feature into main" in log


@needs_bash
def test_push_pushes_and_stops_when_the_remote_is_ahead(tmp_path):
    root = _project(tmp_path)
    code, out = _run(root, "push")
    assert code == 0 and "Nothing to push" in out
    (root / "a.txt").write_text("a")
    _git(root, "add", "a.txt")
    _git(root, "commit", "-qm", "a")
    code, out = _run(root, "push")
    assert code == 0 and "Pushed 1 commit(s) on main to origin" in out
    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", str(tmp_path / "remote.git"), str(other))
    _git(other, "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-q", "--allow-empty", "-m", "x")
    _git(other, "push", "-q", "origin", "main")
    _git(root, "commit", "-q", "--allow-empty", "-m", "b")
    code, out = _run(root, "push")
    assert code == 1 and "origin has 1 commit(s) on main that you don't" in out


@needs_bash
def test_release_bumps_commits_tags_and_pushes(tmp_path):
    root = _project(tmp_path, project_file=PROJECT_FILE + "\n[release]\npublishes = true\n")
    code, out = _run(root, "release")  # no answer to "which version?": cancelled
    assert code == 1 and "Release cancelled" in out
    code, out = _run(root, "release", "--minor", "--no-publish")
    assert code == 0, out
    assert "1.2.0 is committed and tagged here, not pushed" in out
    assert _git(root, "log", "-1", "--format=%s") == "release: 1.2.0"
    assert _git(root, "tag", "--points-at", "HEAD") == "v1.2.0"
    assert "## [1.2.0] - " in (root / "CHANGELOG.md").read_text()
    assert _git(root, "status", "--porcelain") == ""
    # Publishing it from push asks first; with no one to say yes, it doesn't push.
    code, out = _run(root, "push")
    assert code == 1 and "publishing release v1.2.0 was cancelled" in out
    code, out = _run(root, "release", "--patch")
    assert code == 1 and "no entries to release" in out


@needs_bash
def test_a_failing_test_command_stops_a_release_before_anything_changes(tmp_path):
    root = _project(tmp_path, project_file=PROJECT_FILE.replace('test = "true"', 'test = "exit 3"'))
    code, out = _run(root, "release", "--patch", "--publish")
    assert code != 0 and "Tests failed (exit 3)" in out
    assert _git(root, "status", "--porcelain") == "" and _git(root, "tag") == ""


@needs_bash
def test_build_runs_the_build_command(tmp_path):
    root = _project(tmp_path, remote=False)
    code, out = _run(root, "build")
    assert code == 0 and "Build finished" in out
    assert (root / "built.txt").read_text().strip() == "built"


def test_without_a_project_file_it_says_to_run_init(tmp_path):
    root = _project(tmp_path, project_file=None, remote=False)
    code, out = _run(root, "push")
    assert code == 1 and "runner project init" in out


def test_launchers_are_made_through_runner_ctl(tmp_path, monkeypatch):
    root = _project(tmp_path, remote=False)
    sent = []
    monkeypatch.setattr("runner.ctl.send", lambda request: (sent.append(request) or ({"ok": True}, True)))
    lines = project_cli.make_launchers(proj.load(root), "claude", None)
    names = [r["data"]["name"] for r in sent if r["op"] == "launcher.upsert"]
    assert names == ["Demo Build", "Demo Merge", "Demo Push", "Demo Release"]
    first = sent[0]["data"]
    assert first["show_in_main"] is False and f"project build --project {root}" in first["args"]
    assert sent[-1] == {"op": "container.upsert", "source": "claude",
                        "data": {"name": "Demo Scripts", "launchers": names}}
    assert lines[-1].startswith("Container group: Demo Scripts")


def test_the_guides_ship_with_the_package(capsys):
    assert project_cli.main(["guide"]) == 0
    assert capsys.readouterr().out.startswith("# runner project: setting a project up")


# ------------------------------------------------------------------ Help


def test_help_sits_above_exit_and_opens_one_window(qapp, qtbot, tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from runner.config import ConfigManager
    from runner.controller import RunnerController

    monkeypatch.setattr("runner.config.platformdirs.user_config_dir", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr("runner.controller.create_tray", lambda **_: MagicMock())
    controller = RunnerController(qapp, ConfigManager())
    try:
        controller.trigger.request_help.emit()
        window = controller.help_window
        assert window is not None and window.isVisible() and not window.isModal()
        text = window.browser.toPlainText()
        assert text.startswith("Runner Help") and "runner project launchers --as claude" in text
        controller.show_help()
        assert controller.help_window is window
        window.close()
    finally:
        controller.scheduler.stop()
        controller.trigger.hide()
        for panel in controller._all_lists():
            panel.force_hide()
