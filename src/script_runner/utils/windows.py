"""Windows-specific helpers (topmost, icons, etc.).

These are no-ops or safe on non-Windows.
"""

from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtWidgets import QWidget


def ensure_topmost(widget: Optional[QWidget]) -> None:
    """Force a Qt widget to stay on top of other windows (Z-order only).

    On Windows: native SetWindowPos(HWND_TOPMOST, NOACTIVATE) — does not steal focus.

    On macOS: just raise_() (used mainly on hover to bring forward when user wants to use it).
    We avoid automatic re-top after hide/launch on macOS because raise_() can
    interfere with focus/input of other apps and with popup menus.
    """
    if widget is None:
        return

    if sys.platform == "win32":
        try:
            import ctypes

            hwnd = int(widget.winId())
            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_SHOWWINDOW = 0x0040
            SWP_NOACTIVATE = 0x0010  # do not activate / steal focus

            ctypes.windll.user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_NOACTIVATE
            )
        except Exception:
            pass
    else:
        # macOS / others: raise only when we want (e.g. on hover via enterEvent)
        widget.raise_()
