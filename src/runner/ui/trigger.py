"""The small trigger widget showing the downward arrow.

- Frameless Tool window
- Draggable by the user
- Right-click context menu (Add..., Manage..., groups, Exit)
- Emits hover enter/leave for the dropdown controller
- Respects size from settings
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QEvent, QPoint, QRect, Signal, QPointF, QTimer, QObject
from PySide6.QtGui import QAction, QCursor, QMouseEvent, QPaintEvent, QPainter, QPen, QColor, QPolygonF
from PySide6.QtWidgets import QWidget, QMenu, QApplication, QWidgetAction
import sys

from ..config import AppConfig, Launcher
from .toggle_switch import ToggleSwitch


class ArrowContextMenu(QMenu):
    """Arrow menu that stays open while a toggle is clicked.

    Qt hides a popup when a widget action is activated, and a focus change
    from the lists does the same. If the pointer is still inside, pop it
    back open. A normal action, or the pointer leaving, dismisses it.
    """

    dismissed = Signal()
    _REOPEN_LIMIT = 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._popup_pos = QPoint()
        self._inside_rect = QRect()
        self._chose_action = False
        self._reopen_tries = 0
        self._reopening = False
        self._settled = False
        self.triggered.connect(self._on_triggered)

    def _on_triggered(self, action: QAction) -> None:
        # Widget actions are the toggles. Those must not count as a choice
        # that dismisses the menu. Qt emits this only after it has already hidden.
        if isinstance(action, QWidgetAction):
            return
        self._chose_action = True

    def open_at(self, pos: QPoint) -> None:
        self._popup_pos = QPoint(pos)
        if not self._reopening:
            self._reopen_tries = 0
            self._chose_action = False
            self._settled = False
        self._reopening = False
        self.popup(self._popup_pos)

    def pointer_inside(self, rect: QRect | None = None) -> bool:
        bounds = self.frameGeometry() if rect is None else rect
        if bounds.isNull() or bounds.isEmpty():
            return False
        return bounds.contains(QCursor.pos())

    def close_if_pointer_left(self) -> None:
        """Leave-timer callback. A stale leave must not win while the pointer is still here."""
        try:
            if self.isVisible() and self.pointer_inside():
                return
        except RuntimeError:
            return
        self.close()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._press_is_on_toggle(event):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        # Activating the widget action is what hides the menu. The switch
        # already got this click as a child, so do not send it again.
        if self._press_is_on_toggle(event):
            event.accept()
            return
        # Mark a real row before Qt hides the menu. The action's triggered
        # signal runs after that hide, and a dialog it opens would otherwise
        # pop the menu open again on the nested event loop.
        self._mark_chosen_row(event.position().toPoint())
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._mark_chosen_row(None)
        super().keyPressEvent(event)

    def _mark_chosen_row(self, pos: QPoint | None) -> None:
        action = self.activeAction() if pos is None else self.actionAt(pos)
        if action is None or not action.isEnabled() or action.isSeparator():
            return
        if isinstance(action, QWidgetAction):
            return
        self._chose_action = True

    def _press_is_on_toggle(self, event: QMouseEvent) -> bool:
        try:
            action = self.actionAt(event.position().toPoint())
        except RuntimeError:
            return False
        return isinstance(action, QWidgetAction)

    def hideEvent(self, event) -> None:  # type: ignore[override]
        rect = QRect(self.frameGeometry())
        stay = (
            not self._chose_action
            and not self._settled
            and self._reopen_tries < self._REOPEN_LIMIT
            and self.pointer_inside(rect)
        )
        super().hideEvent(event)
        if stay:
            self._reopen_tries += 1
            self._inside_rect = rect
            QTimer.singleShot(0, self._reopen)
            return
        self._notify_dismissed()

    def _reopen(self) -> None:
        if self.isVisible():
            return
        if (
            self._chose_action
            or self._settled
            or self._reopen_tries > self._REOPEN_LIMIT
            or not self.pointer_inside(self._inside_rect)
        ):
            self._notify_dismissed()
            return
        self._reopening = True
        self.open_at(self._popup_pos)

    def _notify_dismissed(self) -> None:
        if self._settled:
            return
        self._settled = True
        self.dismissed.emit()


class TriggerWidget(QWidget):
    """Small floating arrow widget that triggers the dropdown on hover."""

    hover_enter = Signal()
    hover_leave = Signal()
    position_changed = Signal(int, int)  # x, y
    size_changed = Signal(int, int)  # w, h
    request_add = Signal()
    request_manage = Signal()
    request_add_group = Signal()
    request_manage_groups = Signal()
    request_groups = Signal()
    request_add_container = Signal()
    request_manage_containers = Signal()
    request_reset = Signal()
    request_exit = Signal()
    pin_toggled = Signal(bool)
    filter_toggled = Signal(bool)
    greeting_toggled = Signal(bool)
    groups_toggled = Signal(bool)
    startup_toggled = Signal(bool)  # Windows only

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._dragging = False
        self._drag_offset = QPoint()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Critical for macOS: keep this tool window visible even when other
        # applications are active or this app is not the frontmost (agent app).
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        self.setMouseTracking(True)
        self._resize_margin = 8
        self._resizing = False
        self._resize_edge = None
        self._greeting_highlight = False
        self._greeting_flash_on = True
        self._greeting_opacity = 1.0
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
        self.setToolTip(
            "Runner — hover the arrow to open launcher list\n"
            "Right-click for quick toggles (Pin, Filter, Greeting, Show execute groups — menu auto-closes on mouse leave), "
            "Add, Manage, Execute Groups, Container Groups, Reset position & size, Exit"
        )

    def _create_actions(self) -> None:
        self._action_add = QAction("Add new launcher...", self)
        self._action_add.triggered.connect(self.request_add.emit)

        self._action_manage = QAction("Manage launchers...", self)
        self._action_manage.triggered.connect(self.request_manage.emit)

        self._action_reset = QAction("Reset position & size", self)
        self._action_reset.triggered.connect(self.request_reset.emit)

        self._action_add_group = QAction("Add Execute Group", self)
        self._action_add_group.triggered.connect(self.request_add_group.emit)

        self._action_manage_groups = QAction("Manage Execute Groups", self)
        self._action_manage_groups.triggered.connect(self.request_manage_groups.emit)

        self._action_groups = QAction("Execute Groups", self)
        self._action_groups.triggered.connect(self.request_groups.emit)

        self._action_add_container = QAction("Add Container Group", self)
        self._action_add_container.triggered.connect(self.request_add_container.emit)

        self._action_manage_containers = QAction("Manage Container Groups", self)
        self._action_manage_containers.triggered.connect(self.request_manage_containers.emit)

        self._action_exit = QAction("Exit", self)
        self._action_exit.triggered.connect(self.request_exit.emit)

    def _show_context_menu(self, pos: QPoint) -> None:
        """Show the context menu at the given local position.
        Using customContextMenuPolicy + this slot is more reliable on macOS
        (and with frameless/Tool windows) than overriding contextMenuEvent.
        """
        menu = ArrowContextMenu(self)
        menu.addAction(self._action_add)
        menu.addAction(self._action_manage)
        menu.addAction(self._action_reset)
        menu.addSeparator()

        # Sliding toggles inside the menu via QWidgetAction.
        global_pos = self.mapToGlobal(pos)

        pin_switch = ToggleSwitch("Pin dropdown open (fully expanded)")
        pin_switch.setChecked(self._config.settings.pinned_open)
        pin_switch.setPalette(menu.palette())  # inherit menu text color etc.
        pin_action = QWidgetAction(menu)
        pin_action.setDefaultWidget(pin_switch)
        pin_switch.toggled.connect(lambda checked: self.pin_toggled.emit(checked))
        menu.addAction(pin_action)

        filter_switch = ToggleSwitch("Show filter box in dropdown")
        filter_switch.setChecked(getattr(self._config.settings, "show_filter_box", True))
        filter_switch.setPalette(menu.palette())
        filter_action = QWidgetAction(menu)
        filter_action.setDefaultWidget(filter_switch)
        filter_switch.toggled.connect(lambda checked: self.filter_toggled.emit(checked))
        menu.addAction(filter_action)

        greeting_switch = ToggleSwitch("Show greeting message")
        greeting_switch.blockSignals(True)
        greeting_switch.setChecked(getattr(self._config.settings, "show_startup_greeting", True))
        greeting_switch.blockSignals(False)
        greeting_switch.setPalette(menu.palette())
        greeting_action = QWidgetAction(menu)
        greeting_action.setDefaultWidget(greeting_switch)
        greeting_switch.toggled.connect(lambda checked: self.greeting_toggled.emit(checked))
        menu.addAction(greeting_action)

        groups_switch = ToggleSwitch("Show execute groups")
        groups_switch.blockSignals(True)
        groups_switch.setChecked(getattr(self._config.settings, "show_groups", False))
        groups_switch.blockSignals(False)
        groups_switch.setPalette(menu.palette())
        groups_action = QWidgetAction(menu)
        groups_action.setDefaultWidget(groups_switch)
        groups_switch.toggled.connect(lambda checked: self.groups_toggled.emit(checked))
        menu.addAction(groups_action)

        # Windows startup toggle (only really useful on Windows)
        if sys.platform == "win32":
            startup_switch = ToggleSwitch("Launch at Windows startup")
            startup_switch.setChecked(getattr(self._config.settings, "launch_at_startup", False))
            startup_switch.setPalette(menu.palette())
            startup_action = QWidgetAction(menu)
            startup_action.setDefaultWidget(startup_switch)
            startup_switch.toggled.connect(lambda checked: self.startup_toggled.emit(checked))
            menu.addAction(startup_action)

        menu.addSeparator()
        menu.addAction(self._action_add_group)
        menu.addAction(self._action_manage_groups)
        menu.addAction(self._action_groups)
        menu.addAction(self._action_add_container)
        menu.addAction(self._action_manage_containers)
        menu.addSeparator()
        menu.addAction(self._action_exit)

        # Auto-hide the entire menu when the mouse moves away from it (no click required to dismiss).
        # This makes the right-click menu feel lighter for the floating arrow widget.
        # A short grace period timer prevents accidental close while moving between items.
        hide_timer = QTimer(menu)
        hide_timer.setSingleShot(True)
        hide_timer.setInterval(250)
        hide_timer.timeout.connect(menu.close_if_pointer_left)

        class MenuMouseFilter(QObject):
            def __init__(self, menu, timer):
                super().__init__(menu)
                self.menu = menu
                self.timer = timer

            def eventFilter(self, obj, event):
                try:
                    if not self.menu.isVisible():
                        return False
                    menu_rect = self.menu.frameGeometry()
                except RuntimeError:
                    return False
                kind = event.type()
                if kind not in (QEvent.Type.Leave, QEvent.Type.Enter):
                    return False
                # A toggle is a child of the menu. Leave on that child still
                # counts once the pointer has left the menu window itself.
                over_menu = menu_rect.contains(QCursor.pos())
                if kind == QEvent.Type.Leave and not over_menu:
                    self.timer.start()
                elif kind == QEvent.Type.Enter or over_menu:
                    self.timer.stop()
                return False

        mouse_filter = MenuMouseFilter(menu, hide_timer)
        watched = [menu, pin_switch, filter_switch, greeting_switch, groups_switch]
        if sys.platform == "win32":
            watched.append(startup_switch)
        for widget in watched:
            # A focused child inside a popup dismisses the menu on click.
            if widget is not menu:
                widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            widget.installEventFilter(mouse_filter)

        def _detach_menu_filter() -> None:
            for widget in watched:
                try:
                    widget.removeEventFilter(mouse_filter)
                except RuntimeError:
                    pass

        # Keep strong refs on the menu so the filter/timer aren't GC'd prematurely
        menu._mouse_filter = mouse_filter
        menu._hide_timer = hide_timer

        # Stop the leave timer on any hide. Detach and collapse only when the
        # menu is actually done, so a toggle click can pop it open again.
        menu.aboutToHide.connect(hide_timer.stop)
        menu.dismissed.connect(_detach_menu_filter)
        menu.dismissed.connect(self._finish_context_menu)

        # Suppress hover enter/leave while the menu is open. This prevents
        # the dropdown from hiding/showing and interfering with menu selection,
        # which was causing menus to immediately close on macOS.
        # The flag is cleared when the menu is dismissed. If the pointer is
        # already outside the arrow, that close is the leave the lists were waiting for.
        self._in_context_menu = True

        # Use a zero-delay timer + popup(). This is a well-known workaround on
        # macOS for frameless/Tool windows where the context menu would otherwise
        # close immediately as soon as the user moves the mouse or releases the
        # right-click button.
        QTimer.singleShot(0, lambda: menu.open_at(global_pos))

    def _finish_context_menu(self) -> None:
        """The menu ate the arrow's leave event. Collapse once it is gone."""
        self._in_context_menu = False
        if self.frameGeometry().contains(QCursor.pos()):
            return
        self.hover_leave.emit()

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
        # Re-apply persisted size from settings once the native window is realized.
        # Ensures correct geometry for dropdown positioning relative to the trigger.
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
        painter.setBrush(QColor(30, 30, 30, 170))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)

        # Downward arrow (▼)
        painter.setPen(QPen(QColor(230, 230, 230, 210), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
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

    def set_greeting_highlight(self, active: bool, flash_on: bool, opacity: float = 1.0) -> None:
        """The greeting rim is drawn outside this widget. While it is up, the resize grab is wider.

        opacity is kept so the rim can fade without resizing the arrow.
        """
        if active != self._greeting_highlight:
            self._resize_margin = 14 if active else 8
        self._greeting_highlight = active
        self._greeting_flash_on = flash_on
        self._greeting_opacity = 1.0 if not active else max(0.0, min(1.0, float(opacity)))
        self.update()

    def update_size_from_settings(self) -> None:
        self.resize(
            self._config.settings.trigger_width,
            self._config.settings.trigger_height,
        )
