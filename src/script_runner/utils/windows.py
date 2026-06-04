"""Windows-specific helpers (topmost, icons, etc.).

These are no-ops or safe on non-Windows.
"""

from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtWidgets import QWidget


def ensure_topmost(widget: Optional[QWidget]) -> None:
    """Force a Qt widget to stay on top of other windows.

    On Windows this uses the native SetWindowPos(HWND_TOPMOST) which is
    more reliable than Qt's WindowStaysOnTopHint after the app has launched
    other processes or lost focus.
    """
    if widget is None:
        return

    # Always try Qt level
    widget.raise_()
    # activateWindow can help bring it forward in some cases
    widget.activateWindow()

    if sys.platform != "win32":
        return

    try:
        import ctypes

        hwnd = int(widget.winId())
        # Constants
        HWND_TOPMOST = -1
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040
        SWP_NOACTIVATE = 0x0010  # don't steal focus

        ctypes.windll.user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_NOACTIVATE
        )
    except Exception:
        # Never let topmost recovery crash the app
        pass
