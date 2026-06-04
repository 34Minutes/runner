"""Launching logic for configured items.

Supports:
- Plain executables / commands ("calc", "notepad")
- Full paths to .exe / .bat / etc.
- Python scripts (.py) - uses Windows 'py' launcher when appropriate
- URLs / protocols (http, mailto, ms-*, etc.) via shell
- Working directory
- Arguments
- (Windows) Run as administrator
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
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
    p = Path(cmd).expanduser()
    return p.suffix.lower() == ".py" or (not p.is_absolute() and cmd.lower().endswith(".py"))


def _expand_command(command: str) -> str:
    """Expand ~ and environment variables in the command portion."""
    return os.path.expandvars(os.path.expanduser(command))


def launch(launcher: Launcher) -> subprocess.Popen | None:
    """Launch the given launcher item.

    Returns the Popen object on success (or None for shell-handled cases).
    Raises on failure so caller can report error.
    """
    command = _expand_command(launcher.command.strip())
    if not command:
        raise ValueError("Empty command")

    args_str = launcher.args.strip() if launcher.args else ""
    args_list: list[str] = shlex.split(args_str) if args_str else []

    cwd = None
    if launcher.working_dir:
        cwd = os.path.expandvars(os.path.expanduser(launcher.working_dir))
        if cwd and not Path(cwd).exists():
            cwd = None  # fall back

    # URL / protocol / registered shell command -> let the OS handle it
    if _is_url_or_protocol(command):
        # os.startfile works great on Windows for this; on other OS use xdg-open/open
        if sys.platform == "win32":
            os.startfile(command)  # type: ignore[attr-defined]
            return None
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            return subprocess.Popen([opener, command], cwd=cwd)

    # macOS .app bundles (selected via the file dialog)
    if sys.platform == "darwin" and command.lower().endswith(".app"):
        # Use the "open" command to launch the bundle properly.
        # Supports arguments via --args
        open_args = ["open", "-a", command]
        if args_list:
            open_args.append("--args")
            open_args.extend(args_list)
        return subprocess.Popen(open_args, cwd=cwd)

    # Build the argv
    if _is_python_script(command) and not command.lower().startswith(("python", "py ")):
        # Try to use the Windows Python launcher if available, else fall back to sys.executable
        if sys.platform == "win32":
            # 'py' is the preferred PEP 397 launcher on Windows
            argv: list[str] = ["py", "-3", command] + args_list
        else:
            argv = [sys.executable, command] + args_list
    else:
        # Command is the program/executable (can contain spaces, e.g. "C:\Program Files\Brave...\brave.exe"
        # from the Browse button). Additional arguments come from the Parameters field.
        argv = [command] + args_list

    # Creation flags for console visibility (Windows)
    creationflags = 0
    if sys.platform == "win32":
        if launcher.show_console:
            creationflags = subprocess.CREATE_NEW_CONSOLE
        else:
            creationflags = subprocess.CREATE_NO_WINDOW

    popen_kwargs: dict = {
        "cwd": cwd,
        "env": os.environ.copy(),
    }

    if sys.platform == "win32":
        popen_kwargs["creationflags"] = creationflags

    # Run as admin (Windows only)
    if launcher.run_as_admin and sys.platform == "win32":
        return _launch_as_admin_windows(argv, cwd)

    # Normal launch on Windows: use shell=True so that bare commands like "calc", "brave", "explorer"
    # and commands with args (including URLs for browsers) resolve the same way as the Run dialog
    # via App Paths / shell associations.
    if sys.platform == "win32":
        is_python_wrapped = bool(argv) and argv[0].lower() in ("py", "python", "pythonw")
        if launcher.show_console and is_python_wrapped:
            # For python scripts with show_console, use Popen + CREATE_NEW_CONSOLE so output console appears
            cmdline = subprocess.list2cmdline(argv)
            return subprocess.Popen(
                cmdline, shell=True, cwd=cwd,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                env=os.environ.copy()
            )
        cmdline = subprocess.list2cmdline(argv)
        popen_kwargs = {
            "shell": True,
            "cwd": cwd,
            "env": os.environ.copy(),
        }
        if launcher.show_console:
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        else:
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        return subprocess.Popen(cmdline, **popen_kwargs)
    else:
        return subprocess.Popen(argv, **popen_kwargs)


def _shell_execute(command: str, params: str | None = None, cwd: str | None = None, show: int = 1) -> None:
    """Launch using ShellExecuteW. Used for "Run as administrator" and as fallback.
    For normal launches we use subprocess + shell=True to reliably support
    user-specified executables (with spaces) + arguments (e.g. browser + URL).
    """
    import ctypes

    ctypes.windll.shell32.ShellExecuteW(
        None,           # hwnd
        "open",         # verb
        command,
        params,
        cwd,
        show,           # nShowCmd: 1=SW_SHOWNORMAL, 3=SW_MAXIMIZE, etc.
    )


def _launch_as_admin_windows(argv: Sequence[str], cwd: str | None) -> subprocess.Popen | None:
    """Use ShellExecute to launch elevated. Returns None (no Popen handle in this path)."""
    import ctypes
    from ctypes import wintypes

    # Join argv for ShellExecute (it takes a single command line string better for runas)
    # We quote arguments properly
    cmd_line = " ".join(
        f'"{a}"' if " " in a and not (a.startswith('"') and a.endswith('"')) else a for a in argv
    )

    # ShellExecuteW(hwnd, verb, file, params, dir, show)
    # verb="runas" triggers UAC
    ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        argv[0],
        " ".join(argv[1:]) if len(argv) > 1 else None,
        cwd or None,
        1,  # SW_SHOWNORMAL
    )
    # We don't get a handle back easily; success is indicated if no error dialog appeared.
    # For now we treat it as fire-and-forget.
    return None


def get_default_icon_for_launcher(launcher: Launcher) -> str | None:
    """Placeholder for future platform-specific icon extraction (Windows .exe icons etc.)."""
    # On Windows we can later use win32com or Qt's QFileIconProvider
    return None
