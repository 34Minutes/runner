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

    # Build the argv
    if _is_python_script(command) and not command.lower().startswith(("python", "py ")):
        # Try to use the Windows Python launcher if available, else fall back to sys.executable
        if sys.platform == "win32":
            # 'py' is the preferred PEP 397 launcher on Windows
            argv: list[str] = ["py", "-3", command] + args_list
        else:
            argv = [sys.executable, command] + args_list
    else:
        # Direct command or already includes python
        if " " in command and not command.startswith('"') and not Path(command.split()[0]).exists():
            # If it has spaces and isn't a quoted path that exists, treat as command + implicit args?
            # Better: let the user put the whole thing in "command" or use the args field.
            # For simplicity we split the command only if it looks like a single exe with spaces.
            parts = shlex.split(command)
            argv = parts + args_list
        else:
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

    # Normal launch
    if sys.platform == "win32":
        # Use shell=True on Windows so bare commands ("calc", "notepad", "explorer")
        # and commands with args ("explorer .") resolve the same way the Run dialog
        # and Start menu do (via App Paths / shell associations).
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
