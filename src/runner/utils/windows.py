"""Windows-specific helpers (startup integration, single-instance mutex, etc.).

Only imported/used on win32.
"""

from __future__ import annotations

import contextlib
import os
import sys


def _get_startup_command() -> str:
    """Return the command string for the Windows HKCU Run entry.

    When frozen (PyInstaller), runs the bundled .exe directly. In development,
    invokes pythonw.exe (or sys.executable) with the script path so Windows
    does not rely on .py file associations.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        pythonw = exe[:-10] + "pythonw.exe"
        if os.path.exists(pythonw):
            exe = pythonw
    script = os.path.abspath(sys.argv[0])
    return f'"{exe}" "{script}"'


def add_to_startup() -> bool:
    """Create (or update) the current-user Run entry so Runner starts with Windows.

    Returns True on success.
    """
    try:
        import winreg  # type: ignore
    except ImportError:
        return False

    cmd = _get_startup_command()

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "Runner", 0, winreg.REG_SZ, cmd)
        return True
    except OSError:
        return False


def remove_from_startup() -> bool:
    """Remove the Run entry if it exists. Returns True if removed or not present."""
    try:
        import winreg  # type: ignore
    except ImportError:
        return False

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with (
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key,
            contextlib.suppress(FileNotFoundError),  # already gone
        ):
            winreg.DeleteValue(key, "Runner")
        return True
    except OSError:
        return False


def ensure_startup_entry(enabled: bool) -> bool:
    """Idempotent helper: create or remove the Run entry according to the desired state.
    Safe to call on every launch when the setting is True (handles the user moving the exe).
    Returns False when Windows refused the registry change.
    """
    if enabled:
        return add_to_startup()
    return remove_from_startup()


# --- Single instance (mutex) support ---

_single_instance_mutex_handle: int | None = None


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
    except ImportError:
        return True

    try:
        # Without a Global\ prefix the name is private to this sign-in session.
        mutex_name = "Runner_SingleInstance_Mutex_v1"
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
    except (AttributeError, OSError):
        # No usable kernel32 (e.g. during cross-testing) -> allow running
        return True
