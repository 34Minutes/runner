"""Launching logic for configured items.

Supports:
- Plain executables / commands ("calc", "notepad", "python3 tool.py")
- Full paths to .exe / .bat / scripts, including paths with spaces
- Python scripts (.py) - Windows 'py' launcher, otherwise a real Python
  interpreter (never the frozen Runner binary)
- URLs / protocols (http, mailto, ms-*, etc.) via the OS
- macOS apps by .app path or by display name ("Brave Browser")
- Working directory
- Arguments
- (Windows) Run as administrator
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Sequence

from .config import Launcher


def _is_url_or_protocol(cmd: str) -> bool:
    cmd = cmd.strip().lower()
    return (
        cmd.startswith(("http://", "https://", "ftp://", "mailto:", "file:"))
        or cmd.startswith("ms-")  # ms-settings, ms-calendar, etc.
        or "://" in cmd[:10]
    )


def _is_python_script(cmd: str) -> bool:
    return Path(cmd).suffix.lower() == ".py"


def _expand_command(command: str) -> str:
    """Expand ~ and environment variables in the command portion."""
    return os.path.expandvars(os.path.expanduser(command))


def _expand_arg(arg: str) -> str:
    """A leading ~ means the home folder, as it would in a shell."""
    return os.path.expanduser(arg) if arg.startswith("~") else arg


def _split(text: str) -> list[str]:
    """Split a command line into words.

    Windows paths use backslashes, which POSIX splitting treats as escapes.
    There, split without escapes and drop the quotes around each word.
    """
    if sys.platform == "win32":
        parts = shlex.split(text, posix=False)
        return [
            part[1:-1] if len(part) >= 2 and part[0] == part[-1] == '"' else part
            for part in parts
        ]
    return shlex.split(text)


def _command_words(command: str) -> list[str]:
    """The program and any words typed after it in the Command field.

    A command that names an existing file is one word, spaces included, so a
    path chosen with Browse... always works. Otherwise the field is split like
    a shell would, so "python3 tool.py" runs python3 with tool.py.
    """
    if Path(command).exists():
        return [command]
    try:
        words = _split(command)
    except ValueError:
        # Unbalanced quotes. Treat the whole field as the program.
        return [command]
    return words or [command]


# Set inside the packaged app so Runner finds its own bundled Qt. A program
# Runner starts must not inherit them: another Qt program would load Runner's
# Qt next to its own and abort.
_BUNDLE_ONLY_VARS = ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH")
# PyInstaller replaces these and keeps the user's value in <NAME>_ORIG.
_PYINSTALLER_RESTORED_VARS = ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH")


def _child_env() -> dict[str, str] | None:
    """The environment for a launched program. None means inherit as is.

    From source, Runner's environment is the user's, so it is passed on
    unchanged. From the packaged app, the bundle's own settings are removed.
    """
    if not getattr(sys, "frozen", False):
        return None
    env = dict(os.environ)
    for name in _BUNDLE_ONLY_VARS:
        env.pop(name, None)
    for name in _PYINSTALLER_RESTORED_VARS:
        original = env.pop(f"{name}_ORIG", None)
        if original is not None:
            env[name] = original
        else:
            env.pop(name, None)
    return env


def _python_interpreter() -> list[str]:
    """A Python that can run a user script.

    Inside a PyInstaller build sys.executable is the Runner binary itself,
    so look for a Python on PATH instead.
    """
    if sys.platform == "win32":
        return ["py", "-3"]
    if not getattr(sys, "frozen", False):
        return [sys.executable]
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            return [found]
    raise FileNotFoundError(
        "No Python interpreter was found on PATH to run this script. "
        "Install Python 3, or set the command to the full path of python3."
    )


def _is_mac_app(command: str, words: Sequence[str]) -> bool:
    """True when the command names a macOS app rather than a program.

    A .app bundle path counts. So does a name like "Calculator" or
    "Brave Browser" whose first word is not a command on PATH.
    """
    if command.rstrip("/").lower().endswith(".app"):
        return True
    if Path(command).exists() or "/" in command:
        return False
    return shutil.which(words[0]) is None


def launch(launcher: Launcher) -> subprocess.Popen | None:
    """Launch the given launcher item.

    Returns the Popen object on success (or None for shell-handled cases).
    Raises on failure so caller can report error.
    """
    command = _expand_command(launcher.command.strip())
    if not command:
        raise ValueError("Empty command")

    args_str = launcher.args.strip() if launcher.args else ""
    args_list = [_expand_arg(arg) for arg in _split(args_str)] if args_str else []

    cwd = None
    if launcher.working_dir:
        cwd = os.path.expandvars(os.path.expanduser(launcher.working_dir))
        if cwd and not Path(cwd).exists():
            cwd = None  # fall back
    env = _child_env()

    # URL / protocol / registered shell command -> let the OS handle it
    if _is_url_or_protocol(command):
        if sys.platform == "win32":
            os.startfile(command)  # type: ignore[attr-defined]
            return None
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        return subprocess.Popen([opener, command], cwd=cwd, env=env)

    words = _command_words(command)

    if _is_python_script(words[0]):
        argv = _python_interpreter() + words + args_list
    elif sys.platform == "darwin" and _is_mac_app(command, words):
        # open -a "Brave Browser" https://x.com
        # open -a "Brave Browser" --args --incognito https://x.com
        open_args = ["open", "-a", command]
        if args_list:
            if any(arg.startswith("-") for arg in args_list):
                open_args.append("--args")
            open_args.extend(args_list)
        return subprocess.Popen(open_args, cwd=cwd, env=env)
    else:
        argv = words + args_list

    if sys.platform != "win32":
        return subprocess.Popen(argv, cwd=cwd, env=env)

    if launcher.run_as_admin:
        return _launch_as_admin_windows(argv, cwd)

    # No cmd.exe in between, so & | ^ % in arguments reach the program as typed.
    program = shutil.which(argv[0])
    if program is None:
        # Not a program on PATH: an App Paths name ("brave"), a shortcut, or a
        # document. Open it the way the Run dialog would.
        _shell_execute_windows("open", argv, cwd)
        return None
    creationflags = (
        subprocess.CREATE_NEW_CONSOLE if launcher.show_console else subprocess.CREATE_NO_WINDOW
    )
    return subprocess.Popen(
        [program, *argv[1:]],
        cwd=cwd,
        env=env,
        creationflags=creationflags,
    )


@contextmanager
def _bundle_env_removed():
    """Hide the packaged app's own variables from a ShellExecute child.

    ShellExecute takes no environment of its own, so the child gets this
    process's. Remove the bundle's entries for the call, then put them back.
    """
    clean = _child_env()
    if clean is None:
        yield
        return
    saved = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(clean)
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def _shell_execute_windows(verb: str, argv: Sequence[str], cwd: str | None) -> None:
    """ShellExecuteW with this verb. Raises OSError when Windows refuses."""
    import ctypes

    params = subprocess.list2cmdline(list(argv[1:])) if len(argv) > 1 else None
    with _bundle_env_removed():
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            verb,
            argv[0],
            params,
            cwd or None,
            1,  # SW_SHOWNORMAL
        )
    # ShellExecuteW returns a value greater than 32 on success.
    if int(result) <= 32:
        how = " as administrator" if verb == "runas" else ""
        raise OSError(f"Windows could not start '{argv[0]}'{how} (error {int(result)}).")


def _launch_as_admin_windows(argv: Sequence[str], cwd: str | None) -> None:
    """The runas verb shows the UAC prompt. There is no process handle.

    A failure, including a declined UAC prompt, raises OSError so the caller
    can report it.
    """
    _shell_execute_windows("runas", argv, cwd)
    return None


def get_default_icon_for_launcher(launcher: Launcher) -> str | None:
    """Placeholder for future platform-specific icon extraction (Windows .exe icons etc.)."""
    return None
