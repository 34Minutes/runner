"""Windows-specific helpers (startup integration, single-instance mutex, etc.).

Only imported/used on win32.
"""

from __future__ import annotations

import os
import sys
from typing import Optional


def _get_executable_path() -> str:
    """Return the path to the running executable.
    When frozen (PyInstaller onefile), this is the .exe.
    Falls back gracefully for development.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller onefile or onedir
        return sys.executable
    # Development: point at the script or pythonw. For startup we prefer the console-less experience.
    # Users normally run the bundled exe, so this path is mainly for dev testing.
    return os.path.abspath(sys.argv[0])


def is_in_startup() -> bool:
    """Return whether a Run entry for Script Runner exists for the current user."""
    try:
        import winreg  # type: ignore
    except Exception:
        return False

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            try:
                winreg.QueryValueEx(key, "Script Runner")
                return True
            except FileNotFoundError:
                return False
    except Exception:
        return False


def add_to_startup() -> bool:
    """Create (or update) the current-user Run entry so Script Runner starts with Windows.

    Returns True on success.
    """
    try:
        import winreg  # type: ignore
    except Exception:
        return False

    exe = _get_executable_path()
    # Quote if the path contains spaces (standard for Run keys)
    if " " in exe and not (exe.startswith('"') and exe.endswith('"')):
        exe = f'"{exe}"'

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "Script Runner", 0, winreg.REG_SZ, exe)
        return True
    except Exception:
        return False


def remove_from_startup() -> bool:
    """Remove the Run entry if it exists. Returns True if removed or not present."""
    try:
        import winreg  # type: ignore
    except Exception:
        return False

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, "Script Runner")
            except FileNotFoundError:
                pass  # already gone
        return True
    except Exception:
        return False


def ensure_startup_entry(enabled: bool) -> None:
    """Idempotent helper: create or remove the Run entry according to the desired state.
    Safe to call on every launch when the setting is True (handles the user moving the exe).
    """
    if enabled:
        add_to_startup()
    else:
        remove_from_startup()


# --- Single instance (mutex) support ---

_single_instance_mutex_handle: Optional[int] = None


def acquire_single_instance_mutex() -> bool:
    """Try to acquire a Windows named mutex.

    Returns True if we are the first instance (mutex acquired).
    Returns False if another instance already owns it.
    The handle is kept alive in this module so the mutex stays held while the process runs.
    """
    global _single_instance_mutex_handle
    if sys.platform != "win32":
        return True

    try:
        import ctypes
    except Exception:
        return True

    try:
        mutex_name = "ScriptRunner_SingleInstance_Mutex_v1"
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
        if not handle:
            return True

        ERROR_ALREADY_EXISTS = 183
        last_error = ctypes.windll.kernel32.GetLastError()
        if last_error == ERROR_ALREADY_EXISTS:
            ctypes.windll.kernel32.CloseHandle(handle)
            return False

        _single_instance_mutex_handle = handle
        return True
    except Exception:
        # Any failure (e.g. during cross-testing) -> allow running
        return True


def release_single_instance_mutex() -> None:
    global _single_instance_mutex_handle
    if not _single_instance_mutex_handle:
        return
    if sys.platform != "win32":
        _single_instance_mutex_handle = None
        return
    try:
        import ctypes
        ctypes.windll.kernel32.CloseHandle(_single_instance_mutex_handle)
    except Exception:
        pass
    _single_instance_mutex_handle = None
