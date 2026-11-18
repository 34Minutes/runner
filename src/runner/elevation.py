"""Warn when Runner itself runs as administrator (Windows) or root (macOS, Linux).

A program inherits the rights of the program that starts it. Started with
those rights, Runner would give them to every launcher, with no prompt.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable

from PySide6.QtWidgets import QWidget


def is_elevated() -> bool:
    """True when this process has administrator (Windows) or root rights."""
    if sys.platform == "win32":
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            return False
    geteuid = getattr(os, "geteuid", None)
    return geteuid is not None and geteuid() == 0


def warning_text() -> str:
    if sys.platform == "win32":
        return (
            "Runner is running as administrator.\n\n"
            "Every program it starts will also run as administrator, without "
            "asking first. A mistake, or a harmful program, would then have "
            "full control of this PC.\n\n"
            "Unless you meant this, quit Runner and start it normally. A "
            "launcher that needs administrator rights can use Run as "
            "administrator instead, which asks each time."
        )
    return (
        "Runner is running as root.\n\n"
        "Every program it starts will also run as root, with full control of "
        "this computer.\n\n"
        "Unless you meant this, quit Runner and start it as your normal user."
    )


def warn_if_elevated(
    parent: QWidget | None,
    quit_app: Callable[[], None],
    *,
    elevated: Callable[[], bool] = is_elevated,
    ask: Callable[..., bool] | None = None,
) -> bool:
    """Ask whether to quit when Runner has elevated rights. True when the user quit."""
    if not elevated():
        return False
    if ask is None:
        from .ui.stay_on_top import choice as ask
    title = "Runner is running as administrator" if sys.platform == "win32" else "Runner is running as root"
    if not ask(parent, title, warning_text(), "Quit Runner", "Keep Running"):
        return False
    quit_app()
    return True
