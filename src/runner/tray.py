"""System tray icon and menu for Runner."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .ui.theme import current


def tray_icon() -> QIcon:
    """Menu-bar arrow in the active scheme's accent color."""
    icon_size = 18
    pix = QPixmap(icon_size, icon_size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(current().tray_icon), 2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    margin = 3
    center_x = icon_size // 2
    painter.drawLine(margin, margin + 1, center_x, icon_size - margin)
    painter.drawLine(center_x, icon_size - margin, icon_size - margin, margin + 1)
    painter.end()
    return QIcon(pix)


def create_tray(
    *,
    on_add: Callable[[], None],
    on_manage: Callable[[], None],
    on_reset: Callable[[], None],
    on_reload: Callable[[], None],
    on_exit: Callable[[], None],
    on_click: Callable[[], None],
) -> QSystemTrayIcon:
    """The tray icon and its menu. A left click opens the launcher list."""
    tray = QSystemTrayIcon()
    tray.setIcon(tray_icon())

    menu = QMenu()
    for text, slot in (
        ("Add Launcher…", on_add),
        ("Manage Launchers…", on_manage),
        ("Reset Position and Size", on_reset),
        ("Reload Config", on_reload),
    ):
        action = QAction(text, menu)
        action.triggered.connect(lambda _checked=False, slot=slot: slot())
        menu.addAction(action)
    menu.addSeparator()
    exit_action = QAction("Exit Runner", menu)
    exit_action.triggered.connect(lambda _checked=False: on_exit())
    menu.addAction(exit_action)
    # The tray does not own its menu. Keep it alive as long as the tray.
    tray._menu = menu  # type: ignore[attr-defined]

    tray.setContextMenu(menu)
    tray.setToolTip("Runner")

    def on_activated(reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            on_click()

    tray.activated.connect(on_activated)
    tray.show()
    return tray
