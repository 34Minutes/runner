"""The small trigger widget showing the downward arrow.

- Frameless Tool window
- Draggable by the user
- Right-click context menu (Add..., Manage..., Exit)
- Emits hover enter/leave for the dropdown controller
- Respects size from settings
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
    size_changed = Signal(int, int)  # w, h
    request_add = Signal()
    request_manage = Signal()
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
        self._resize_margin = 8
        self._resizing = False
        self._resize_edge = None
        self.setMinimumSize(20, 20)
        self.resize(
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

        self._in_context_menu = False

        # Move to saved position (clamped later by caller if needed)
        self.move(config.settings.position_x, config.settings.position_y)

        # Optional: slight tooltip
        self.setToolTip("Script Runner — hover the arrow to open launcher list\nRight-click for Add / Manage / Exit")

    def _create_actions(self) -> None:
        self._action_add = QAction("Add new launcher...", self)
        self._action_add.triggered.connect(self.request_add.emit)

        self._action_manage = QAction("Manage launchers...", self)
        self._action_manage.triggered.connect(self.request_manage.emit)

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
            edge = self._get_resize_edge(event.pos())
            if edge:
                self._resizing = True
                self._resize_edge = edge
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
            else:
                self._dragging = True
                self._drag_offset = event.globalPosition().toPoint() - self.pos()
                event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._resizing:
            self._perform_resize(event)
            event.accept()
        elif self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
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
            self._update_resize_cursor(event.pos())
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            if self._resizing:
                self._resizing = False
                self._resize_edge = None
                self.size_changed.emit(self.width(), self.height())
                self.setCursor(Qt.ArrowCursor)
                event.accept()
            elif self._dragging:
                self._dragging = False
                event.accept()
            else:
                super().mouseReleaseEvent(event)
        else:
            super().mouseReleaseEvent(event)

    def _get_resize_edge(self, pos: QPoint):
        rect = self.rect()
        m = self._resize_margin
        left = pos.x() < m
        right = pos.x() > rect.width() - m
        top = pos.y() < m
        bottom = pos.y() > rect.height() - m
        if top and left: return "topleft"
        if top and right: return "topright"
        if bottom and left: return "bottomleft"
        if bottom and right: return "bottomright"
        if left: return "left"
        if right: return "right"
        if top: return "top"
        if bottom: return "bottom"
        return None

    def _update_resize_cursor(self, pos: QPoint):
        edge = self._get_resize_edge(pos)
        if edge in ("topleft", "bottomright"):
            self.setCursor(Qt.SizeFDiagCursor)
        elif edge in ("topright", "bottomleft"):
            self.setCursor(Qt.SizeBDiagCursor)
        elif edge in ("left", "right"):
            self.setCursor(Qt.SizeHorCursor)
        elif edge in ("top", "bottom"):
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def _perform_resize(self, event: QMouseEvent):
        global_pos = event.globalPosition().toPoint()
        rect = self.geometry()
        edge = self._resize_edge
        if "left" in edge:
            rect.setLeft(global_pos.x())
        if "right" in edge:
            rect.setRight(global_pos.x())
        if "top" in edge:
            rect.setTop(global_pos.y())
        if "bottom" in edge:
            rect.setBottom(global_pos.y())
        # enforce min size
        if rect.width() < self.minimumWidth():
            if "left" in edge:
                rect.setLeft(rect.right() - self.minimumWidth())
            else:
                rect.setRight(rect.left() + self.minimumWidth())
        if rect.height() < self.minimumHeight():
            if "top" in edge:
                rect.setTop(rect.bottom() - self.minimumHeight())
            else:
                rect.setBottom(rect.top() + self.minimumHeight())
        self.setGeometry(rect)

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

    def showEvent(self, event: QEvent) -> None:  # type: ignore[override]
        super().showEvent(event)
        # Re-apply the (possibly persisted custom) size from settings once the
        # top-level window is realized. This ensures .width()/.height() and
        # mapToGlobal return the correct values for initial dropdown positioning
        # (avoids the arrow appearing under the list on startup after resizes).
        self.resize(
            self._config.settings.trigger_width,
            self._config.settings.trigger_height,
        )
        self.raise_()

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
        self.resize(
            self._config.settings.trigger_width,
            self._config.settings.trigger_height,
        )
