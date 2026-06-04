"""The small trigger widget showing the downward arrow.

- Frameless Tool window (not always-on-top anymore)
- Draggable by the user
- Right-click context menu (Add..., Manage..., Exit)
- Emits hover enter/leave for the dropdown controller
- Respects size from settings
- Global hotkey support (registered in main.py) to force-show the list
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QEvent, QPoint, Signal, QPointF
from PySide6.QtGui import QAction, QMouseEvent, QPaintEvent, QPainter, QPen, QColor, QPolygonF
from PySide6.QtWidgets import QWidget, QMenu, QApplication

from ..config import AppConfig, Launcher


class TriggerWidget(QWidget):
    """Small floating arrow widget that triggers the dropdown on hover."""

    hover_enter = Signal()
    hover_leave = Signal()
    position_changed = Signal(int, int)  # x, y
    request_add = Signal()
    request_manage = Signal()
    request_set_hotkey = Signal()
    request_exit = Signal()

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._dragging = False
        self._drag_offset = QPoint()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setFixedSize(
            config.settings.trigger_width,
            config.settings.trigger_height,
        )

        # Use custom context menu policy. Overriding contextMenuEvent can cause
        # the menu to immediately close on some platforms (especially macOS)
        # with frameless/Tool windows.
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._in_context_menu = False

        # Context menu actions
        self._create_actions()

        # Move to saved position (clamped later by caller if needed)
        self.move(config.settings.position_x, config.settings.position_y)

        # Optional: slight tooltip
        self.setToolTip("Script Runner — hover the arrow to open launcher list\n"
                        "Right-click for Add / Manage / Exit / Set hotkey\n"
                        "Global hotkey (configurable) shows the list")

    def _create_actions(self) -> None:
        self._action_add = QAction("Add new launcher...", self)
        self._action_add.triggered.connect(self.request_add.emit)

        self._action_manage = QAction("Manage launchers...", self)
        self._action_manage.triggered.connect(self.request_manage.emit)

        self._action_set_hotkey = QAction("Set hotkey...", self)
        self._action_set_hotkey.triggered.connect(self.request_set_hotkey.emit)

        self._action_exit = QAction("Exit", self)
        self._action_exit.triggered.connect(self.request_exit.emit)

    def _show_context_menu(self, pos: QPoint) -> None:
        """Show the context menu at the given local position.
        Using customContextMenuPolicy + this slot is more reliable on macOS
        (and with frameless/Tool windows) than overriding contextMenuEvent.
        """
        menu = QMenu(self)
        menu.addAction(self._action_add)
        menu.addAction(self._action_manage)
        menu.addAction(self._action_set_hotkey)
        menu.addSeparator()
        menu.addAction(self._action_exit)

        # Suppress hover enter/leave while the menu is open. This prevents
        # the dropdown from hiding/showing and interfering with menu selection,
        # which was causing menus to immediately close on macOS.
        self._in_context_menu = True
        menu.aboutToHide.connect(lambda: setattr(self, '_in_context_menu', False))

        # Use a zero-delay timer + popup(). This is a well-known workaround on
        # macOS for frameless/Tool windows where the context menu would otherwise
        # close immediately as soon as the user moves the mouse or releases the
        # right-click button.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: menu.popup(self.mapToGlobal(pos)))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            # Optional: keep on screen (simple version, full multi-monitor later)
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                new_pos.setX(max(geo.left(), min(new_pos.x(), geo.right() - self.width())))
                new_pos.setY(max(geo.top(), min(new_pos.y(), geo.bottom() - self.height())))
            self.move(new_pos)
            self.position_changed.emit(new_pos.x(), new_pos.y())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def enterEvent(self, event: QEvent) -> None:  # type: ignore[override]
        if getattr(self, '_in_context_menu', False):
            return
        self.hover_enter.emit()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # type: ignore[override]
        if getattr(self, '_in_context_menu', False):
            return
        self.hover_leave.emit()
        super().leaveEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Subtle background pill / rounded rect
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(30, 30, 30, 220))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)

        # Downward arrow (▼)
        painter.setPen(QPen(QColor(230, 230, 230), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        w = self.width()
        h = self.height()
        cx = w / 2
        cy = h / 2 + 1

        # Simple triangle arrow
        arrow_size = min(w, h) * 0.38
        path_points = [
            (cx - arrow_size * 0.6, cy - arrow_size * 0.35),
            (cx + arrow_size * 0.6, cy - arrow_size * 0.35),
            (cx, cy + arrow_size * 0.55),
        ]
        poly = QPolygonF([QPointF(x, y) for x, y in path_points])
        painter.drawPolygon(poly)

    def update_size_from_settings(self) -> None:
        self.setFixedSize(
            self._config.settings.trigger_width,
            self._config.settings.trigger_height,
        )
