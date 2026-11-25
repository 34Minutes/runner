"""`runner template` and the script templates it copies, run for real on a demo project."""

import os
import re
import signal
import subprocess
import sys

import pytest

from runner import template_cli

needs_bash = pytest.mark.skipif(sys.platform == "win32", reason="the templates need bash")

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


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def _project(tmp_path, *, remote=True):
    """A git project with a remote."""
    root = tmp_path / "demo"
    (root / "demo").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "1.1.2"\n'
                                         '[tool.ruff]\ntarget-version = "py312"\n')
    (root / "demo" / "__init__.py").write_text('__version__ = "1.1.2"\n')
    (root / "CHANGELOG.md").write_text(CHANGELOG)
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


def _script(root, name, **settings):
    """Copy a template into root/scripts, set its settings, and commit it."""
    path = template_cli.copy(name, root / "scripts")
    text = path.read_text()
    for key, value in settings.items():
        text, n = re.subn(rf"^{key}=.*$", f"{key}={value}", text, count=1, flags=re.MULTILINE)
        assert n == 1, key
    path.write_text(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", f"add {name}")
    return path


def _run(path, *args):
    """Run a copied script quietly, from somewhere else, as a launcher would."""
    env = dict(os.environ, SCRIPTS_QUIET="1", SCRIPTS_LOG_DIR=str(path.parent.parent.parent / "logs"))
    # Its own process group, so a timeout stops everything it started.
    proc = subprocess.Popen([str(path), *args], cwd=path.anchor, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise
    return proc.returncode, out


# ------------------------------------------------------------------ runner template


def test_list_names_every_template_with_a_line_about_it(capsys):
    assert template_cli.main(["list"]) == 0
    out = capsys.readouterr().out
    for name in ("build", "merge", "push", "release", "test-once"):
        line = next(x for x in out.splitlines() if x.startswith(name + " "))
        assert line.rstrip().endswith(".")


def test_show_prints_a_template_and_an_unknown_one_is_explained(capsys):
    assert template_cli.main(["show", "release"]) == 0
    assert capsys.readouterr().out.startswith("#!/bin/bash\n# Release: ")
    assert template_cli.main(["show", "deploy"]) == 1
    assert "runner template list" in capsys.readouterr().err


def test_copy_makes_runnable_scripts_and_wont_overwrite_without_force(tmp_path, capsys):
    assert template_cli.main(["copy", "build", "merge", "--to", str(tmp_path / "s")]) == 0
    assert "runner ctl --as <you> launcher upsert" in capsys.readouterr().out
    path = tmp_path / "s" / "build.sh"
    assert os.access(path, os.X_OK) or sys.platform == "win32"
    path.write_text("mine")
    assert template_cli.main(["copy", "build", "--to", str(tmp_path / "s")]) == 1
    assert "--force" in capsys.readouterr().err and path.read_text() == "mine"
    assert template_cli.main(["copy", "build", "--to", str(tmp_path / "s"), "--force"]) == 0
    assert path.read_text() != "mine"


def test_the_main_program_runs_it():
    done = subprocess.run([sys.executable, "-m", "runner", "template", "list"],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and "release" in done.stdout


# ------------------------------------------------------------------ the templates, for real


@needs_bash
def test_build_runs_lint_tests_and_build_and_logs(tmp_path):
    root = _project(tmp_path, remote=False)
    path = _script(root, "build", LINT_CMD='"true"', TEST_CMD='"true"', BUILD_CMD='"echo built > built.txt"')
    code, out = _run(path)
    assert code == 0 and "Build finished" in out, out
    assert (root / "built.txt").read_text().strip() == "built"
    assert "Build finished" in (tmp_path / "logs" / "build.log").read_text()


@needs_bash
def test_build_stops_without_a_command_and_says_which_step_failed(tmp_path):
    root = _project(tmp_path, remote=False)
    code, out = _run(_script(root, "build"))
    assert code == 1 and "BUILD_CMD is empty" in out
    (root / "scripts" / "build.sh").unlink()
    path = _script(root, "build", BUILD_CMD='"exit 4"')
    code, out = _run(path)
    assert code == 4 and "Build failed (exit 4)" in out


@needs_bash
def test_merge_fast_forwards_and_stops_for_anything_else(tmp_path):
    root = _project(tmp_path)
    path = _script(root, "merge")
    code, out = _run(path)
    assert code == 1 and "You're on main" in out
    _git(root, "checkout", "-qb", "feature")
    (root / "f.txt").write_text("f")
    _git(root, "add", "f.txt")
    _git(root, "commit", "-qm", "f")
    (root / "CHANGELOG.md").write_text(CHANGELOG + "dirty")
    code, out = _run(path)
    assert code == 1 and "uncommitted changes" in out
    _git(root, "checkout", "-q", "CHANGELOG.md")
    code, out = _run(path)
    assert code == 0 and "Merged feature into main (1 commit(s))" in out
    assert _git(root, "branch", "--show-current") == "main"


@needs_bash
def test_push_pushes_and_stops_when_the_remote_is_ahead(tmp_path):
    root = _project(tmp_path)
    path = _script(root, "push")
    _git(root, "push", "-q", "origin", "main")
    code, out = _run(path)
    assert code == 0 and "Nothing to push" in out, out
    _git(root, "commit", "-q", "--allow-empty", "-m", "a")
    code, out = _run(path)
    assert code == 0 and "Pushed 1 commit(s) on main to origin" in out
    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", str(tmp_path / "remote.git"), str(other))
    _git(other, "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-q", "--allow-empty", "-m", "x")
    _git(other, "push", "-q", "origin", "main")
    _git(root, "commit", "-q", "--allow-empty", "-m", "b")
    code, out = _run(path)
    assert code == 1 and "origin has 1 commit(s) on main that you don't" in out


@needs_bash
def test_push_asks_before_publishing_a_release_tag(tmp_path):
    root = _project(tmp_path)
    path = _script(root, "push", PUBLISHES="1")
    _git(root, "tag", "-a", "v1.1.2", "-m", "1.1.2")
    code, out = _run(path)  # quiet: no one to say yes
    assert code == 1 and "publishing release v1.1.2 was cancelled" in out
    assert _git(root, "ls-remote", "--tags", "origin") == ""
    path.write_text(path.read_text().replace("PUBLISHES=1", "PUBLISHES=0", 1))
    code, out = _run(path)
    assert code == 0 and "Tags: v1.1.2" in out and "v1.1.2" in _git(root, "ls-remote", "--tags", "origin")


@needs_bash
def test_release_bumps_every_version_file_dates_the_changelog_commits_and_tags(tmp_path):
    root = _project(tmp_path)
    path = _script(root, "release", VERSION_FILES='("pyproject.toml" "demo/__init__.py")',
                   LINT_CMD='"true"', TEST_CMD='"true"')
    code, out = _run(path)  # no answer to "which version?": cancelled
    assert code == 1 and "Release cancelled" in out
    code, out = _run(path, "--minor", "--no-publish")
    assert code == 0, out
    assert "1.2.0 is committed and tagged here, not pushed" in out
    assert 'version = "1.2.0"' in (root / "pyproject.toml").read_text()
    assert 'target-version = "py312"' in (root / "pyproject.toml").read_text()
    assert (root / "demo" / "__init__.py").read_text() == '__version__ = "1.2.0"\n'
    log = (root / "CHANGELOG.md").read_text()
    unreleased, rest = log.split("## [1.2.0] - ")
    assert "### Planned\n- Icons." in unreleased and "A new thing" not in unreleased
    assert "### Added\n- A new thing.\n\n### Fixed\n- A bug.\n\n## [1.1.2]" in rest
    assert _git(root, "log", "-1", "--format=%s") == "release: 1.2.0"
    assert _git(root, "tag", "--points-at", "HEAD") == "v1.2.0"
    assert _git(root, "status", "--porcelain") == ""
    code, out = _run(path, "--patch")
    assert code == 1 and "no entries under Unreleased" in out


@needs_bash
def test_a_failing_test_command_stops_a_release_before_anything_changes(tmp_path):
    root = _project(tmp_path)
    path = _script(root, "release", TEST_CMD='"exit 3"')
    code, out = _run(path, "--patch", "--publish")
    assert code == 3 and "Tests failed (exit 3)" in out
    assert _git(root, "status", "--porcelain") == "" and _git(root, "tag") == ""


@needs_bash
def test_release_stops_when_the_version_files_disagree(tmp_path):
    root = _project(tmp_path)
    (root / "demo" / "__init__.py").write_text('__version__ = "1.1.1"\n')
    _git(root, "commit", "-qam", "drift")
    _git(root, "push", "-q", "origin", "main")
    path = _script(root, "release", VERSION_FILES='("pyproject.toml" "demo/__init__.py")')
    _git(root, "push", "-q", "origin", "main")
    code, out = _run(path, "--patch")
    assert code == 1 and "demo/__init__.py says 1.1.1, but pyproject.toml says 1.1.2" in out


@needs_bash
def test_test_once_skips_code_that_passed_and_runs_one_at_a_time(tmp_path):
    root = _project(tmp_path, remote=False)
    path = _script(root, "test-once", TEST_CMD='"echo ran >> runs.txt"', WATCH='("demo")')
    runs = root / "runs.txt"
    assert _run(path)[0] == 0 and runs.read_text() == "ran\n"
    code, out = _run(path)
    assert code == 0 and "already passed" in out and runs.read_text() == "ran\n"
    (root / "demo" / "__init__.py").write_text('__version__ = "9.9.9"\n')
    assert _run(path)[0] == 0 and runs.read_text() == "ran\nran\n"
    assert _run(path, "--force")[0] == 0 and runs.read_text().count("ran") == 3
    # A run that's going blocks a second; one that died doesn't.
    lock = root / ".git" / "test-once" / "lock"
    lock.mkdir()
    (lock / "pid").write_text(str(os.getpid()))
    code, out = _run(path, "--force")
    assert code == 75 and f"already running (pid {os.getpid()})" in out
    (lock / "pid").write_text("999999")
    assert _run(path, "--force")[0] == 0 and not lock.exists()


@needs_bash
def test_a_failing_test_once_run_is_not_remembered(tmp_path):
    root = _project(tmp_path, remote=False)
    path = _script(root, "test-once", TEST_CMD='"echo x >> runs.txt; exit 2"', WATCH='("demo")')
    assert _run(path)[0] == 2
    assert _run(path)[0] == 2 and (root / "runs.txt").read_text() == "x\nx\n"


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
        assert text.startswith("Runner Help") and "runner template copy" in text
        controller.show_help()
        assert controller.help_window is window
        window.close()
    finally:
        controller.scheduler.stop()
        controller.trigger.hide()
        for panel in controller._all_lists():
            panel.force_hide()


def test_every_command_help_tells_llms_about_exists():
    """The commands in Help's LLM block must all be real: each answers --help."""
    from runner.ui.help_dialog import help_text

    block = help_text().split("## Runner (my desktop launcher)")[1]
    lines = re.findall(r"^  runner (.+?)\s{2,}", block, flags=re.MULTILINE)
    assert len(lines) == 6
    for line in lines:
        words = [w for w in line.split() if w != "--as" and w != "claude" and not w.isupper()]
        words = [w for w in words if not w.startswith("--") and not w.endswith("...")]
        done = subprocess.run([sys.executable, "-m", "runner", *words, "--help"],
                              capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, (line, done.stdout + done.stderr)
