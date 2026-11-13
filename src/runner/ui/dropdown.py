"""Animated dropdown panel containing the launcher buttons.

Shown below the trigger on hover. Handles its own mouse tracking so the list
stays visible while the mouse travels from the arrow into the list.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QEvent, QPropertyAnimation, QEasingCurve, QTimer, Signal, QPoint, QRect
from PySide6.QtGui import QCursor, QKeyEvent
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QScrollArea,
    QWidget as QW,
    QFrame,
    QLabel,
    QLineEdit,
    QMenu,
    QApplication,
    QPushButton,
)

from ..config import AppConfig, Launcher
from .launch_button import LaunchButton
from .stay_on_top import mark_stay_on_top


class SubmenuButton(QPushButton):
    """A main-list row that opens another list on hover. It does not launch."""

    hovered = Signal(str)
    left = Signal(str)

    def __init__(self, item_id: str, name: str, parent=None) -> None:
        super().__init__(f"{name}    ›", parent)
        self.item_id = item_id
        self.item_name = name
        self.setObjectName("submenuRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(28)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(48, 52, 64, 210);
                color: #eee;
                border: 1px solid rgba(90, 100, 120, 180);
                border-radius: 5px;
                padding: 4px 10px;
                text-align: left;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: rgba(70, 110, 170, 210);
                border: 1px solid rgba(100, 140, 200, 220);
            }
            """
        )
        self.setToolTip("Hover to open\nRight-click to edit or delete")

    def enterEvent(self, event: QEvent) -> None:  # type: ignore[override]
        self.hovered.emit(self.item_id)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # type: ignore[override]
        self.left.emit(self.item_id)
        super().leaveEvent(event)

# Vertical pixels before a press becomes a reorder drag, so a click still launches.
_DRAG_THRESHOLD_PX = 10
# A small step out of the column. Large enough to read as lifted, small enough
# that the row still feels under the pointer.
_DRAG_LIFT_X = 8
_DRAG_SLIDE_MS = 150


def merge_visible_order(entries: list[tuple[str, bool]], visible_ids: list[str]) -> list[str]:
    """Reorder the flagged rows and leave every other row where it is.

    entries is (id, in_play) in the current order. visible_ids is the new
    top-to-bottom order of the in-play rows. Disabled launchers, and enabled
    ones hidden by the filter, stay in their slots.
    """
    in_play = {eid for eid, flagged in entries if flagged}
    queue = [vid for vid in visible_ids if vid in in_play]
    pending = iter(queue)
    merged: list[str] = []
    for eid, flagged in entries:
        if flagged and eid in in_play:
            merged.append(next(pending))
        else:
            merged.append(eid)
    return merged


class DropdownPanel(QWidget):
    """The expanding list of launch buttons. Animated show/hide."""

    launch_requested = Signal(Launcher)  # emitted when a button is clicked
    reordered = Signal(list)  # full launcher id order after a drag
    edit_requested = Signal(Launcher)
    delete_requested = Signal(Launcher)
    submenu_hovered = Signal(str)
    submenu_left = Signal(str)
    submenu_edit_requested = Signal(str)
    submenu_delete_requested = Signal(str)
    hover_enter = Signal()
    hover_leave = Signal()
    closed = Signal()

    def __init__(
        self,
        config: AppConfig,
        parent: QWidget | None = None,
        *,
        honor_pin: bool = True,
        allow_reorder: bool = True,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._honor_pin = honor_pin
        self._allow_reorder = allow_reorder
        self._submenu_items: list[tuple[str, str]] = []
        self._order_ids: Callable[[], list[str]] | None = None
        self._row_tooltip: Callable[[Launcher], str] | None = None
        self._empty_hint = "No launchers yet.\nRight-click the arrow → Add new launcher..."
        self._buttons: list[LaunchButton] = []
        self._animation: QPropertyAnimation | None = None
        self._anims: list[QPropertyAnimation] = []
        self._motion = 0
        self._close_motion = 0
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._do_hide)
        self._anchor_trigger: QWidget | None = None  # for re-positioning after show() on some platforms
        self._position_hook: Callable[[], None] | None = None
        self._grow_from_top: bool = True
        self._fixed_edge_y: int = 0
        self._grow_direction: str = "below"

        # Keyboard navigation state
        self._current_button: LaunchButton | None = None
        self._visible_buttons: list[LaunchButton] = []  # subset of _buttons that are currently visible (post-filter)

        # Click-drag reorder. A short press still launches; a vertical drag moves the row.
        self._drag_button: LaunchButton | None = None
        self._drag_press_y = 0
        self._drag_last_global = QPoint()
        self._drag_active = False
        self._drag_detached = False
        self._drag_order: list[LaunchButton] = []
        self._drag_base_y = 0
        self._drag_home_x = 0
        self._drag_row_step = 0
        self._drag_row_h = 0
        self._row_anims: dict[LaunchButton, QPropertyAnimation] = {}
        self._suppress_click = False
        self._in_context_menu = False
        self._item_menu: QMenu | None = None
        self._drag_scroll_timer = QTimer(self)
        self._drag_scroll_timer.setInterval(40)
        self._drag_scroll_timer.timeout.connect(self._drag_autoscroll)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            # Note: we intentionally allow focus for keyboard (Esc, arrows)
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Help keep the dropdown visible on macOS when the app is backgrounded
        # (pairs with LSUIElement + trigger's MacAlwaysShowToolWindow).
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        self.setMouseTracking(True)

        # Main container frame for nice border/background
        self._frame = QFrame(self)
        self._frame.setFrameShape(QFrame.Shape.StyledPanel)
        self._frame.setFrameShadow(QFrame.Shadow.Raised)
        self._frame.setStyleSheet(
            """
            QFrame {
                background-color: rgba(35, 35, 38, 245);
                border: 1px solid rgba(80, 80, 85, 200);
                border-radius: 8px;
            }
            """
        )

        self._layout = QVBoxLayout(self._frame)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(3)

        self._heading = QLabel(self._frame)
        self._heading.setObjectName("listHeading")
        self._heading.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._heading.setStyleSheet(
            "QLabel#listHeading {"
            " color: #b4b4ba;"
            " font-size: 11px;"
            " background: transparent;"
            " border: none;"
            " padding: 0px 2px 0px 2px;"
            "}"
        )
        self._heading.hide()

        self._search_edit = QLineEdit(self._frame)
        self._search_edit.setPlaceholderText("Filter launchers...")
        self._search_edit.setStyleSheet(
            "QLineEdit { background: rgba(25,25,28,200); color: #ddd; border: 1px solid rgba(70,70,75,180); border-radius: 4px; padding: 3px 6px; font-size: 12px; }"
            "QLineEdit:focus { border: 1px solid rgba(90,120,180,200); }"
        )
        self._search_edit.textChanged.connect(self._apply_filter)
        self._search_edit.installEventFilter(self)

        # Scroll area in case there are many items
        self._scroll = QScrollArea(self._frame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            "QScrollBar::handle:vertical { background: rgba(120,120,125,160); border-radius: 3px; }"
        )

        self._button_container = QWidget()
        self._button_container.setStyleSheet("background: transparent;")
        self._button_layout = QVBoxLayout(self._button_container)
        self._button_layout.setContentsMargins(0, 0, 0, 0)
        self._button_layout.setSpacing(2)

        self._scroll.setWidget(self._button_container)
        self._layout.addWidget(self._heading)
        self._layout.addWidget(self._search_edit)
        self._layout.addWidget(self._scroll)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

        self.hide()  # start hidden
        self.setFixedWidth(config.settings.dropdown_width)

        self._hide_timer.setInterval(140)  # small grace period

        # Respect initial show_filter_box setting
        self.refresh_filter_visibility()

    def _pinned(self) -> bool:
        return self._honor_pin and self._config.settings.pinned_open

    def set_heading(self, text: str) -> None:
        """Small corner label above the rows. Empty text hides it."""
        self._heading.setText(text)
        self._heading.setVisible(bool(text))
        if self.isVisible():
            self._update_height_for_content()

    def use_position_hook(self, hook: Callable[[], None] | None) -> None:
        """Replace the default beside-the-arrow placement. None restores it."""
        self._position_hook = hook

    def set_list_copy(self, *, placeholder: str, empty_hint: str) -> None:
        """Filter box placeholder and the text shown when the list is empty."""
        self._empty_hint = empty_hint
        self._search_edit.setPlaceholderText(placeholder)

    def set_submenu_items(self, items: list[tuple[str, str]]) -> None:
        """Rows shown above the launchers. Each is (id, name). Hover opens a side list."""
        self._submenu_items = list(items)

    def submenu_button(self, item_id: str) -> SubmenuButton | None:
        for button in self._buttons:
            if isinstance(button, SubmenuButton) and button.item_id == item_id:
                return button
        return None

    def set_order_ids(self, provider: Callable[[], list[str]] | None) -> None:
        """Reorder these ids instead of the main launcher list."""
        self._order_ids = provider

    def set_row_tooltip(self, provider: Callable[[Launcher], str] | None) -> None:
        """Replace the default launch tooltip. Used by the group list."""
        self._row_tooltip = provider

    def set_width(self, width: int) -> None:
        self.setFixedWidth(width)

    def refresh_filter_visibility(self) -> None:
        """Sync whether the filter search box is shown based on current settings.
        Safe to call after the setting is toggled in Manage. Will resize if the
        dropdown is currently visible.
        """
        show = getattr(self._config.settings, "show_filter_box", True)
        if show:
            self._search_edit.show()
        else:
            self._search_edit.hide()
        if self.isVisible():
            self._update_height_for_content()

    def update_height_for_content(self) -> None:
        """Recompute and apply the correct height for the current buttons (public)."""
        self._update_height_for_content()

    def rebuild_buttons(self, launchers: list[Launcher]) -> None:
        """Replace all buttons with current enabled launchers."""
        self._cancel_drag()
        # Clear previous selection styling
        self._clear_keyboard_selection()

        # Clear
        for b in self._buttons:
            b.deleteLater()
        self._buttons.clear()
        self._visible_buttons.clear()

        for item_id, name in self._submenu_items:
            button = SubmenuButton(item_id, name, self._button_container)
            button.hovered.connect(self.submenu_hovered)
            button.left.connect(self.submenu_left)
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda pos, row=button: self._show_submenu_menu(row, pos)
            )
            self._button_layout.addWidget(button)
            self._buttons.append(button)

        for launcher in launchers:
            btn = LaunchButton(launcher, self._button_container)
            btn.clicked.connect(lambda checked=False, l=launcher: self._on_button_clicked(l))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, b=btn: self._show_item_menu(b, pos)
            )
            btn.installEventFilter(self)
            if self._row_tooltip is not None:
                btn.setToolTip(self._row_tooltip(launcher))
            self._button_layout.addWidget(btn)
            self._buttons.append(btn)

        # A blank hint means show nothing when the list is empty.
        if not launchers and not self._submenu_items and self._empty_hint.strip():
            hint = QLabel(self._empty_hint)
            hint.setStyleSheet("color: #888; font-size: 11px; padding: 8px;")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._button_layout.addWidget(hint)
            self._buttons.append(hint)  # type: ignore  # for cleanup

        self._update_height_for_content()
        # Re-apply any active filter after buttons change (e.g. after add/edit/manage)
        self._apply_filter(self._search_edit.text())

    def _apply_filter(self, text: str) -> None:
        """Hide non-matching buttons (by name); show matching. Then recompute height.

        Empty text shows all. Nothing is highlighted just because the list
        opened or the filter changed. A row the user already moved to stays
        highlighted only while it remains visible.
        """
        q = (text or "").strip().lower()
        previous = self._current_button
        self._clear_keyboard_selection()
        self._visible_buttons.clear()

        for w in self._buttons:
            if isinstance(w, LaunchButton):
                match = q == "" or q in w.launcher.name.lower() or q in (w.launcher.command or "").lower()
                w.setVisible(match)
                if match:
                    self._visible_buttons.append(w)
            elif isinstance(w, SubmenuButton):
                match = q == "" or q in w.item_name.lower()
                was_visible = w.isVisible()
                w.setVisible(match)
                if was_visible and not match:
                    self.submenu_left.emit(w.item_id)
            elif isinstance(w, QLabel):
                # the empty hint label
                w.setVisible(q == "")

        self._update_height_for_content()
        if previous is not None and previous in self._visible_buttons and previous.isVisible():
            self._set_keyboard_current(previous)

    def _update_height_for_content(self) -> None:
        """Compute the height required so that each button row gets its full height
        (minHeight or sizeHint) + the declared _button_layout spacing (2px) + chrome.

        We sum explicitly from the child widgets because once the _button_container
        has been set as the widget of the QScrollArea (during __init__, before
        rebuild adds children), the container's layout.minimumSize() and sizeHint()
        can report artificially low values (e.g. 68 instead of 88 for 3x28+spacings).
        Using those would cause us to set too-small fixed height on frame/scroll,
        making the inner VBox allocate too little vertical space → children get
        placed with ~20px steps; their minHeight=28 then causes overlaps/squish
        (gaps of -8 instead of +2).
        """
        # Ensure search visibility matches the latest setting (e.g. toggled from Manage while list open)
        show = getattr(self._config.settings, "show_filter_box", True)
        if show != self._search_edit.isVisible():
            if show:
                self._search_edit.show()
            else:
                self._search_edit.hide()

        self._button_container.adjustSize()
        if self._search_edit.isVisible():
            self._search_edit.adjustSize()

        # Explicit sum: robust even when hosted layout reports wrong aggregates.
        inner_h = 0
        sp = self._button_layout.spacing()
        visible_count = 0
        for w in self._buttons:
            if hasattr(w, 'isVisible') and not w.isVisible():
                continue
            if visible_count > 0:
                inner_h += sp
            if hasattr(w, 'sizeHint'):
                try:
                    sh_h = w.sizeHint().height()
                except Exception:
                    sh_h = 0
                mh = getattr(w, 'minimumHeight', lambda: 0)()
                inner_h += max(sh_h, mh, 20)
            else:
                inner_h += 20
            visible_count += 1

        m = self._layout.contentsMargins()
        frame_chrome = m.top() + m.bottom()
        search_h = 0
        heading_h = 0
        gaps = 0
        if not self._heading.isHidden():
            self._heading.adjustSize()
            heading_h = self._heading.height() or self._heading.sizeHint().height() or 16
            gaps += 1
        if self._search_edit.isVisible():
            self._search_edit.adjustSize()
            search_h = self._search_edit.height() or self._search_edit.sizeHint().height() or 22
            gaps += 1
        layout_sp = self._layout.spacing() * gaps
        # The button_layout (inside container inside scroll) observes an ~8px top inset
        # (first button y≈8). To give the VBoxLayout a rect tall enough for mins + its
        # own spacing(2), we need extra on top of the pure inner_h.
        viewport_chrome = 22  # extra allowance so the inner button_layout rect is large enough for all minHeights + the full declared spacing(2) between each (previously we were 1px short per gap)
        target_h = inner_h + frame_chrome + viewport_chrome + search_h + heading_h + layout_sp
        max_h = 420
        target_h = min(target_h, max_h)
        self._frame.setFixedHeight(target_h)
        self.setFixedHeight(target_h)

        # Give the inner content a minimumHeight so that when the QScrollArea (resizable)
        # is constrained by the frame's fixed height (or during/after anims), the
        # button_layout still receives enough vertical space to place children with
        # their full minHeight *and* the declared spacing(2).
        self._button_container.setMinimumHeight(inner_h)
        self._scroll.setMinimumHeight(inner_h)

        # Force layout to adopt the size so child layouts (button spacing) get the correct allocation now
        self._frame.updateGeometry()
        self.updateGeometry()

    def _on_button_clicked(self, launcher: Launcher) -> None:
        if self._suppress_click:
            self._suppress_click = False
            return
        self.launch_requested.emit(launcher)
        # Note: hide decision (respecting pinned state) is now handled in main.py's on_launch

    def _launch_buttons(self) -> list[LaunchButton]:
        return [b for b in self._buttons if isinstance(b, LaunchButton)]

    def _cancel_drag(self) -> None:
        button = self._drag_button
        self._drag_scroll_timer.stop()
        self._drag_active = False
        self._drag_button = None
        self._stop_row_anims()
        if self._drag_detached:
            self._commit_drag_order()
        if button is None:
            return
        if self.mouseGrabber() is button:
            button.releaseMouse()
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_drag_style(button, False)

    def _set_drag_style(self, button: LaunchButton, dragging: bool) -> None:
        button.setProperty("dragging", "true" if dragging else "false")
        button.style().polish(button)
        button.update()

    def _begin_drag(self, button: LaunchButton) -> None:
        self._drag_active = True
        self._cancel_hide()
        button.setDown(False)
        self._set_drag_style(button, True)
        button.setCursor(Qt.CursorShape.ClosedHandCursor)
        button.grabMouse()
        self._detach_for_drag(button)
        self._drag_scroll_timer.start()

    def _stop_row_anims(self) -> None:
        running = list(self._row_anims.values())
        self._row_anims.clear()
        for anim in running:
            anim.stop()

    def _detach_for_drag(self, button: LaunchButton) -> None:
        """Lift this row out of the column and leave a gap the others can slide around."""
        visible = [item for item in self._launch_buttons() if item.isVisible()]
        if button not in visible:
            return
        self._drag_order = list(visible)
        self._drag_home_x = button.x()
        self._drag_row_h = max(button.height(), 1)
        self._drag_row_step = self._drag_row_h + self._button_layout.spacing()
        self._drag_base_y = min(item.y() for item in visible)
        content_h = self._drag_base_y + len(visible) * self._drag_row_step
        self._button_container.setMinimumHeight(max(self._button_container.minimumHeight(), content_h))
        for item in visible:
            self._button_layout.removeWidget(item)
        self._drag_detached = True
        self._slide_rest(animate=False)
        self._place_lifted(button)

    def _slide_rest(self, animate: bool) -> None:
        dragged = self._drag_button
        if dragged is None:
            return
        slot = 0
        for button in self._drag_order:
            if button is dragged:
                slot += 1
                continue
            target = QPoint(self._drag_home_x, self._drag_base_y + slot * self._drag_row_step)
            slot += 1
            self._move_row(button, target, animate)

    def _move_row(self, button: LaunchButton, target: QPoint, animate: bool) -> None:
        running = self._row_anims.pop(button, None)
        if running is not None:
            running.stop()
        if not animate or button.pos() == target:
            button.move(target)
            return
        anim = QPropertyAnimation(button, b"pos", button)
        anim.setDuration(_DRAG_SLIDE_MS)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(button.pos())
        anim.setEndValue(target)
        anim.start()
        self._row_anims[button] = anim

    def _place_lifted(self, button: LaunchButton) -> None:
        local_y = self._button_container.mapFromGlobal(self._drag_last_global).y()
        y = local_y - button.height() // 2
        limit = self._drag_base_y + max(0, len(self._drag_order) - 1) * self._drag_row_step
        y = max(self._drag_base_y, min(y, limit))
        button.move(self._drag_home_x + _DRAG_LIFT_X, y)
        button.raise_()

    def _commit_drag_order(self) -> None:
        if not self._drag_detached:
            return
        self._drag_detached = False
        visible_order = list(self._drag_order)
        self._drag_order = []
        if not visible_order:
            return
        in_play = {button.launcher.id for button in visible_order}
        entries = [(button.launcher.id, button.launcher.id in in_play) for button in self._launch_buttons()]
        new_ids = merge_visible_order(entries, [button.launcher.id for button in visible_order])
        by_id = {button.launcher.id: button for button in self._launch_buttons()}
        ordered = [by_id[item_id] for item_id in new_ids if item_id in by_id]
        self._place_launcher_rows(ordered)

    def _finish_drag(self, global_pos: QPoint) -> None:
        button = self._drag_button
        self._suppress_click = True
        self._cancel_drag()
        self._emit_reordered()
        if button is None or self._pinned():
            return
        local = self.mapFromGlobal(global_pos)
        if not self.rect().contains(local):
            self._schedule_hide()
            self.hover_leave.emit()

    def _emit_reordered(self) -> None:
        visible_ids = [b.launcher.id for b in self._launch_buttons() if b.isVisible()]
        visible_set = set(visible_ids)
        if self._order_ids is not None:
            current_ids = list(self._order_ids())
            entries = [(item_id, item_id in visible_set) for item_id in current_ids]
        else:
            current_ids = [launcher.id for launcher in self._config.launchers]
            entries = [
                (launcher.id, launcher.enabled and launcher.id in visible_set)
                for launcher in self._config.launchers
            ]
        new_ids = merge_visible_order(entries, visible_ids)
        if new_ids != current_ids:
            self.reordered.emit(new_ids)

    def _target_visible_index(self, global_y: int) -> int:
        """Index to insert the dragged row at. len(visible) means after the last row."""
        if self._drag_detached and self._drag_order:
            origin = self._button_container.mapToGlobal(QPoint(0, self._drag_base_y)).y()
            count = len(self._drag_order)
            for index in range(count):
                center = origin + index * self._drag_row_step + self._drag_row_h / 2
                if global_y < center:
                    return index
            return count
        visible = [b for b in self._launch_buttons() if b.isVisible()]
        for index, button in enumerate(visible):
            center = button.mapToGlobal(QPoint(0, button.height() // 2)).y()
            if global_y < center:
                return index
        return len(visible)

    def _move_dragged_to(self, index: int) -> None:
        dragged = self._drag_button
        if dragged is None:
            return
        visible = list(self._drag_order) if self._drag_detached else [b for b in self._launch_buttons() if b.isVisible()]
        if dragged not in visible:
            return
        old = visible.index(dragged)
        # index is an insertion point, so the slot just after the row is the same place.
        if index == old or index == old + 1:
            return
        visible.pop(old)
        if old < index:
            index -= 1
        index = max(0, min(index, len(visible)))
        visible.insert(index, dragged)
        if self._drag_detached:
            self._drag_order = visible
            self._slide_rest(animate=True)
            return

        entries = [(b.launcher.id, b.isVisible()) for b in self._launch_buttons()]
        new_ids = merge_visible_order(entries, [b.launcher.id for b in visible])
        by_id = {b.launcher.id: b for b in self._launch_buttons()}
        ordered = [by_id[item_id] for item_id in new_ids if item_id in by_id]
        self._place_launcher_rows(ordered)

    def _place_launcher_rows(self, launchers: list[LaunchButton]) -> None:
        """Keep container rows above the launchers when a drag reorders the list."""
        prefixes = [button for button in self._buttons if isinstance(button, SubmenuButton)]
        labels = [
            button
            for button in self._buttons
            if not isinstance(button, (LaunchButton, SubmenuButton))
        ]
        self._relayout_buttons(prefixes + launchers + labels)

    def _relayout_buttons(self, buttons: list) -> None:
        for button in buttons:
            self._button_layout.removeWidget(button)
        for button in buttons:
            self._button_layout.addWidget(button)
        self._buttons = list(buttons)
        self._visible_buttons = [b for b in self._buttons if isinstance(b, LaunchButton) and b.isVisible()]

    def _drag_step(self, global_pos: QPoint) -> None:
        self._drag_last_global = global_pos
        self._autoscroll_once(global_pos)
        self._move_dragged_to(self._target_visible_index(global_pos.y()))
        if self._drag_button is not None and self._drag_detached:
            self._place_lifted(self._drag_button)

    def _autoscroll_once(self, global_pos: QPoint) -> None:
        viewport = self._scroll.viewport()
        local_y = viewport.mapFromGlobal(global_pos).y()
        bar = self._scroll.verticalScrollBar()
        if local_y < 16:
            bar.setValue(bar.value() - 14)
        elif local_y > viewport.height() - 16:
            bar.setValue(bar.value() + 14)

    def _drag_autoscroll(self) -> None:
        if not self._drag_active or self._drag_button is None:
            self._drag_scroll_timer.stop()
            return
        self._drag_step(self._drag_last_global)

    def _handle_reorder_event(self, button: LaunchButton, event: QEvent) -> bool:
        if not self._allow_reorder:
            return False
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._suppress_click = False
            self._drag_button = button
            self._drag_press_y = event.globalPosition().toPoint().y()
            self._drag_last_global = event.globalPosition().toPoint()
            self._drag_active = False
            return False
        if (
            kind == QEvent.Type.MouseMove
            and self._drag_button is button
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            global_pos = event.globalPosition().toPoint()
            if not self._drag_active:
                if abs(global_pos.y() - self._drag_press_y) < _DRAG_THRESHOLD_PX:
                    return False
                self._begin_drag(button)
            self._drag_step(global_pos)
            return True
        if (
            kind == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
            and self._drag_button is button
            and self._drag_active
        ):
            # Swallow the release so the row does not launch at the end of a drag.
            self._finish_drag(event.globalPosition().toPoint())
            return True
        return False

    def _show_item_menu(self, button: LaunchButton, pos: QPoint) -> None:
        """Right-click menu for one row. Edit and Delete only."""
        if self._drag_active:
            return
        previous = self._item_menu
        if previous is not None:
            try:
                previous.aboutToHide.disconnect(self._on_item_menu_hidden)
            except RuntimeError:
                pass
            previous.close()

        launcher = button.launcher
        menu = QMenu(self)
        mark_stay_on_top(menu)
        edit_action = menu.addAction("Edit")
        delete_action = menu.addAction("Delete")
        edit_action.triggered.connect(lambda checked=False, item=launcher: self.edit_requested.emit(item))
        delete_action.triggered.connect(lambda checked=False, item=launcher: self.delete_requested.emit(item))

        self._item_menu = menu
        self._in_context_menu = True
        self._cancel_hide()
        menu.aboutToHide.connect(self._on_item_menu_hidden)
        global_pos = button.mapToGlobal(pos)
        # Frameless tool windows close a context menu immediately on macOS
        # unless popup is deferred until after the right-click release.
        QTimer.singleShot(0, lambda m=menu, p=global_pos: m.popup(p))

    def _show_submenu_menu(self, button: SubmenuButton, pos: QPoint) -> None:
        """Right-click menu for a container group row. Edit and Delete only."""
        if self._drag_active:
            return
        previous = self._item_menu
        if previous is not None:
            try:
                previous.aboutToHide.disconnect(self._on_item_menu_hidden)
            except RuntimeError:
                pass
            previous.close()

        item_id = button.item_id
        menu = QMenu(self)
        mark_stay_on_top(menu)
        edit_action = menu.addAction("Edit")
        delete_action = menu.addAction("Delete")
        edit_action.triggered.connect(
            lambda checked=False, group_id=item_id: self.submenu_edit_requested.emit(group_id)
        )
        delete_action.triggered.connect(
            lambda checked=False, group_id=item_id: self.submenu_delete_requested.emit(group_id)
        )

        self._item_menu = menu
        self._in_context_menu = True
        self._cancel_hide()
        menu.aboutToHide.connect(self._on_item_menu_hidden)
        global_pos = button.mapToGlobal(pos)
        QTimer.singleShot(0, lambda m=menu, p=global_pos: m.popup(p))

    def _on_item_menu_hidden(self) -> None:
        self._in_context_menu = False
        if self._pinned():
            return
        if self.frameGeometry().contains(QCursor.pos()):
            return
        self._schedule_hide()
        self.hover_leave.emit()

    # --- Keyboard navigation helpers ---

    def _clear_keyboard_selection(self) -> None:
        if self._current_button is not None:
            try:
                self._current_button.set_keyboard_selected(False)
            except Exception:
                pass
        self._current_button = None

    def _set_keyboard_current(self, btn: LaunchButton | None) -> None:
        """Set the visually (and navigationally) current button for keyboard ops."""
        if self._current_button is btn:
            return
        self._clear_keyboard_selection()
        self._current_button = btn
        if btn is not None:
            btn.set_keyboard_selected(True)
            # Ensure it's scrolled into view (important for long lists)
            try:
                self._scroll.ensureWidgetVisible(btn)
            except Exception:
                pass

    def _get_visible_launch_buttons(self) -> list[LaunchButton]:
        """Return currently visible LaunchButtons (post filter)."""
        # Prefer the maintained list; fall back to live scan if needed
        if self._visible_buttons:
            return [b for b in self._visible_buttons if b.isVisible()]
        return [b for b in self._buttons if isinstance(b, LaunchButton) and b.isVisible()]

    def _select_first_visible(self) -> None:
        vis = self._get_visible_launch_buttons()
        if vis:
            self._set_keyboard_current(vis[0])
        else:
            self._clear_keyboard_selection()

    def _select_last_visible(self) -> None:
        vis = self._get_visible_launch_buttons()
        if vis:
            self._set_keyboard_current(vis[-1])
        else:
            self._clear_keyboard_selection()

    def _move_selection(self, delta: int) -> None:
        vis = self._get_visible_launch_buttons()
        if not vis:
            return
        try:
            idx = vis.index(self._current_button) if self._current_button in vis else -1
        except ValueError:
            idx = -1
        new_idx = idx + delta
        if new_idx < 0:
            new_idx = 0
        if new_idx >= len(vis):
            new_idx = len(vis) - 1
        self._set_keyboard_current(vis[new_idx])

    def position_adjacent(self, trigger: QWidget) -> None:
        """Position the dropdown relative to the trigger.

        Default: below the arrow, horizontally centered on it.

        If not enough room below (near bottom of screen), flip to above.

        Horizontally shift left/right as needed so the dropdown stays fully on-screen.

        Sets internal flags (_grow_from_top, _fixed_edge_y, _grow_direction) so that
        the show/hide animations grow/shrink *away* from the screen edge (attached to the arrow).
        """
        self._anchor_trigger = trigger

        # Make sure we know our final content size for fitting calculations.
        self._update_height_for_content()

        target_w = self.width()
        target_h = self._frame.height() or 120

        # Trigger in global coordinates.
        trig_pos = trigger.mapToGlobal(QPoint(0, 0))
        trig_rect = QRect(trig_pos, trigger.size())

        # Available screen area (excludes taskbar/dock etc.).
        screen = QApplication.screenAt(trig_pos) or QApplication.primaryScreen()
        avail = screen.availableGeometry()

        overlap = 3

        # --- Preferred below + centered ---
        below_y = trig_rect.bottom() - overlap
        center_x = trig_rect.left() + (trig_rect.width() - target_w) // 2
        below_rect = QRect(center_x, below_y, target_w, target_h)

        # Horizontal clamp for below case (prefer left-align if dropdown wider than screen)
        if below_rect.right() > avail.right():
            below_rect.moveRight(avail.right())
        if below_rect.left() < avail.left():
            below_rect.moveLeft(avail.left())

        space_below = avail.bottom() - trig_rect.bottom()
        fits_below = below_rect.bottom() <= avail.bottom()

        # --- Alternative above ---
        above_y = trig_rect.top() + overlap - target_h
        above_rect = QRect(center_x, above_y, target_w, target_h)

        # Horizontal clamp for above case (prefer left-align if dropdown wider than screen)
        if above_rect.right() > avail.right():
            above_rect.moveRight(avail.right())
        if above_rect.left() < avail.left():
            above_rect.moveLeft(avail.left())

        space_above = trig_rect.top() - avail.top()
        fits_above = above_rect.top() >= avail.top()

        # Choose direction. Prefer below. Fall back to the side with more space.
        if fits_below or (not fits_above and space_below >= space_above):
            direction = "below"
            final_rect = below_rect
        else:
            direction = "above"
            final_rect = above_rect

        # Final vertical clamp (extreme cases: huge list or tiny screen)
        if final_rect.top() < avail.top():
            final_rect.moveTop(avail.top())
        if final_rect.bottom() > avail.bottom():
            final_rect.moveBottom(avail.bottom())

        # Apply position
        self.move(final_rect.topLeft())

        # Compute edge from (possibly clamped) rect so the growth origin matches
        # the actual placed position. This is used by the show/hide animations.
        if direction == "below":
            fixed_edge_y = final_rect.top()
            grow_from_top = True
        else:
            fixed_edge_y = final_rect.bottom()
            grow_from_top = False

        # Store for animations so they expand/contract away from the edge.
        self._grow_direction = direction
        self._fixed_edge_y = fixed_edge_y
        self._grow_from_top = grow_from_top

    def _place(self) -> None:
        if self._position_hook is not None:
            self._position_hook()
        elif self._anchor_trigger is not None:
            self.position_adjacent(self._anchor_trigger)

    def position_beside(self, neighbor: QWidget, trigger: QWidget) -> None:
        """Sit beside the launcher list, toward the middle of the screen.

        The arrow's half of the screen picks the side: groups go left of the
        launchers when the arrow is on the right, and right when it is on the
        left. The list opens up or down with the launcher list.
        """
        self._update_height_for_content()
        target_w = self.width()
        target_h = self._frame.height() or self.height() or 120

        trig_pos = trigger.mapToGlobal(QPoint(0, 0))
        screen = QApplication.screenAt(trig_pos) or QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        arrow_x = trig_pos.x() + max(trigger.width(), 1) // 2
        place_left = arrow_x >= avail.center().x()
        gap = 6
        if place_left:
            x = neighbor.x() - gap - target_w
        else:
            x = neighbor.x() + neighbor.width() + gap

        grow_from_top = bool(getattr(neighbor, "_grow_from_top", True))
        if grow_from_top:
            y = neighbor.y()
        else:
            edge = int(getattr(neighbor, "_fixed_edge_y", neighbor.y() + neighbor.height()))
            y = edge - target_h

        rect = QRect(x, y, target_w, target_h)
        if rect.left() < avail.left():
            rect.moveLeft(avail.left())
        if rect.right() > avail.right():
            rect.moveRight(avail.right())
        if rect.top() < avail.top():
            rect.moveTop(avail.top())
        if rect.bottom() > avail.bottom():
            rect.moveBottom(avail.bottom())

        self.move(rect.topLeft())
        self._grow_from_top = grow_from_top
        self._grow_direction = "below" if grow_from_top else "above"
        self._fixed_edge_y = rect.top() if grow_from_top else rect.bottom()

    def position_next_to(self, host: QWidget, anchor: QWidget, *, prefer_right: bool = True) -> None:
        """Open beside the launcher list, lined up with one row.

        prefer_right places it on the right of the list. The other side is used
        when the preferred side would leave the screen.
        """
        self._update_height_for_content()
        target_w = self.width()
        target_h = self._frame.height() or self.height() or 120
        host_geo = host.frameGeometry()
        anchor_top = anchor.mapToGlobal(QPoint(0, 0)).y()
        screen = QApplication.screenAt(host_geo.center()) or QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        gap = 4

        def place(on_right: bool) -> QRect:
            if on_right:
                x = host_geo.right() + gap
            else:
                x = host_geo.left() - gap - target_w
            return QRect(x, anchor_top, target_w, target_h)

        rect = place(prefer_right)
        if prefer_right and rect.right() > avail.right():
            rect = place(False)
        elif not prefer_right and rect.left() < avail.left():
            rect = place(True)
        if rect.left() < avail.left():
            rect.moveLeft(avail.left())
        if rect.right() > avail.right():
            rect.moveRight(avail.right())
        if rect.top() < avail.top():
            rect.moveTop(avail.top())
        if rect.bottom() > avail.bottom():
            rect.moveBottom(avail.bottom())

        self.move(rect.topLeft())
        self._grow_from_top = rect.top() <= anchor_top + 2
        self._grow_direction = "below" if self._grow_from_top else "above"
        self._fixed_edge_y = rect.top() if self._grow_from_top else rect.bottom()

    # --- Hover handling (combined area: trigger + this panel) ---
    def enterEvent(self, event: QEvent) -> None:  # type: ignore[override]
        self._cancel_hide()
        self.hover_enter.emit()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # type: ignore[override]
        if self._drag_active or self._in_context_menu:
            return
        if not self._pinned():
            self._schedule_hide()
        self.hover_leave.emit()
        super().leaveEvent(event)

    def _schedule_hide(self) -> None:
        if self._pinned() or self._drag_active or self._in_context_menu:
            return
        self._hide_timer.start()

    def _cancel_hide(self) -> None:
        self._hide_timer.stop()

    def cancel_hide(self) -> None:
        """Cancel any pending hide timer. Called from main when mouse moves from dd list back to trigger."""
        self._cancel_hide()

    def ensure_visible_and_sized(self) -> None:
        """Ensure the dropdown is visible at the correct full content height.
        Safe to call when pinned_open: prevents unwanted collapses after moves,
        resizes of trigger, or click interactions.
        """
        self._cancel_hide()
        self._update_height_for_content()
        if not self.isVisible():
            self.show()
            self.raise_()  # bring list forward (caller will raise trigger after to keep arrow on top)
            self._place()
            self.raise_()
            self.setWindowOpacity(1.0)
        else:
            self._place()
            # Clear anim constraints so our fixed target from _update rules
            self._frame.setMinimumHeight(0)
            self._frame.setMaximumHeight(16777215)
            self._frame.updateGeometry()
            self.updateGeometry()
        if self._current_button is not None and not self._current_button.isVisible():
            self._clear_keyboard_selection()

    def _do_hide(self) -> None:
        self.start_hide_animation()

    def is_closing(self) -> bool:
        """True while a hide animation is committed to emitting closed."""
        return self._close_motion != 0 and self._close_motion == self._motion

    def _invalidate_motion(self) -> int:
        """Stop show/hide animations. Their finish handlers then do nothing."""
        self._motion += 1
        running = self._anims
        self._anims = []
        for anim in running:
            anim.stop()
        return self._motion

    def _track_anim(self, anim: QPropertyAnimation) -> None:
        self._anims.append(anim)

    # --- Animations ---
    def start_show_animation(self) -> None:
        self._cancel_hide()
        motion = self._invalidate_motion()
        self._close_motion = 0
        # Pin and Show groups open this panel from a toggle on the arrow menu.
        # Taking focus would dismiss that popup while the pointer is still on it.
        menu_open = isinstance(QApplication.activePopupWidget(), QMenu)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, menu_open)
        self.show()
        self.raise_()
        self._place()
        self.raise_()
        if not menu_open:
            self.setFocus(Qt.FocusReason.OtherFocusReason)

        self._update_height_for_content()

        self._button_container.setMinimumHeight(0)
        self._scroll.setMinimumHeight(0)

        start_h = 8
        end_h = self._frame.height()

        grow_from_top = getattr(self, "_grow_from_top", True)
        fixed_edge = getattr(self, "_fixed_edge_y", self.y())

        if grow_from_top:
            # Below: top edge fixed at the attachment point. Grow downward.
            self.move(self.x(), fixed_edge)
            self._frame.setFixedHeight(start_h)
            self.setWindowOpacity(0.0)
            pos_anim = None
        else:
            # Above: bottom edge fixed at the attachment point. Grow upward.
            # Start small with its bottom at the fixed edge.
            init_y = fixed_edge - start_h
            self.move(self.x(), init_y)
            self._frame.setFixedHeight(start_h)
            self.setWindowOpacity(0.0)
            # We also need to animate the y position upward as height grows.
            final_y = fixed_edge - end_h
            pos_anim = QPropertyAnimation(self, b"pos", self)
            pos_anim.setDuration(self._config.settings.animation_duration_ms)
            pos_anim.setStartValue(QPoint(self.x(), init_y))
            pos_anim.setEndValue(QPoint(self.x(), final_y))
            pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._frame.setMaximumHeight(end_h)

        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(self._config.settings.animation_duration_ms)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        height_anim = QPropertyAnimation(self._frame, b"minimumHeight", self)
        height_anim.setDuration(self._config.settings.animation_duration_ms)
        height_anim.setStartValue(start_h)
        height_anim.setEndValue(end_h)
        height_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def on_finished(motion: int = motion) -> None:
            if motion != self._motion:
                return
            self._frame.setMinimumHeight(0)
            self._frame.setMaximumHeight(16777215)
            self._frame.setFixedHeight(end_h)
            self.setWindowOpacity(1.0)
            # Restore proper mins for the content now that we are at full open height.
            # This re-enables the "don't squish my spacings" protection.
            self._update_height_for_content()

        height_anim.finished.connect(on_finished)

        self._animation = anim  # keep ref
        self._track_anim(anim)
        self._track_anim(height_anim)
        anim.start()
        height_anim.start()
        if pos_anim is not None:
            self._track_anim(pos_anim)
            pos_anim.start()

    def start_hide_animation(self) -> None:
        if self._pinned():
            return
        if not self.isVisible():
            return

        motion = self._invalidate_motion()
        self._close_motion = motion

        self._button_container.setMinimumHeight(0)
        self._scroll.setMinimumHeight(0)

        current_h = self._frame.height()
        start_op = self.windowOpacity()

        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(int(self._config.settings.animation_duration_ms * 0.7))
        anim.setStartValue(start_op)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)

        height_anim = QPropertyAnimation(self._frame, b"minimumHeight", self)
        height_anim.setDuration(int(self._config.settings.animation_duration_ms * 0.75))
        height_anim.setStartValue(current_h)
        height_anim.setEndValue(6)
        height_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        pos_anim = None
        grow_from_top = getattr(self, "_grow_from_top", True)
        if not grow_from_top:
            fixed_bottom = getattr(self, "_fixed_edge_y", self.y() + current_h)
            curr_y = self.y()
            end_y = fixed_bottom - 6
            pos_anim = QPropertyAnimation(self, b"pos", self)
            pos_anim.setDuration(int(self._config.settings.animation_duration_ms * 0.7))
            pos_anim.setStartValue(QPoint(self.x(), curr_y))
            pos_anim.setEndValue(QPoint(self.x(), end_y))
            pos_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        def on_finished(motion: int = motion) -> None:
            if motion != self._motion:
                return
            self._close_motion = 0
            self._search_edit.clear()
            self._clear_keyboard_selection()
            self._visible_buttons.clear()
            self.hide()
            self.setWindowOpacity(1.0)
            self._frame.setMinimumHeight(0)
            self._frame.setMaximumHeight(16777215)
            self._frame.setFixedHeight(self._frame.sizeHint().height() or 120)
            self.closed.emit()

        height_anim.finished.connect(on_finished)

        self._animation = anim
        self._track_anim(anim)
        self._track_anim(height_anim)
        anim.start()
        height_anim.start()
        if pos_anim is not None:
            self._track_anim(pos_anim)
            pos_anim.start()

    def force_hide(self) -> None:
        """Immediate hide (used on launch or escape)."""
        was_visible = self.isVisible()
        self._cancel_hide()
        self._invalidate_motion()
        self._close_motion = 0
        self._search_edit.clear()
        self._clear_keyboard_selection()
        self._visible_buttons.clear()
        self.hide()
        self.setWindowOpacity(1.0)
        self._grow_from_top = True
        self._fixed_edge_y = 0
        self._grow_direction = "below"
        if was_visible:
            self.closed.emit()

    def keyPressEvent(self, event):  # type: ignore[override]
        key = event.key()

        if key == Qt.Key.Key_Escape:
            if self._search_edit.text():
                self._search_edit.clear()
                event.accept()
                return
            if not self._pinned():
                self.force_hide()
            event.accept()
            return

        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_Home, Qt.Key.Key_End,
                   Qt.Key.Key_Return, Qt.Key.Key_Enter):
            vis = self._get_visible_launch_buttons()
            if not vis:
                super().keyPressEvent(event)
                return

            if key == Qt.Key.Key_Down:
                if self._current_button is None or self._current_button not in vis:
                    self._set_keyboard_current(vis[0])
                else:
                    self._move_selection(+1)
                event.accept()
                return
            if key == Qt.Key.Key_Up:
                if self._current_button is None or self._current_button not in vis:
                    self._set_keyboard_current(vis[0])
                else:
                    self._move_selection(-1)
                event.accept()
                return
            if key == Qt.Key.Key_Home:
                self._select_first_visible()
                event.accept()
                return
            if key == Qt.Key.Key_End:
                self._select_last_visible()
                event.accept()
                return
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._current_button is not None and self._current_button.isVisible():
                    # Emit launch for the keyboard-chosen item
                    self._on_button_clicked(self._current_button.launcher)
                event.accept()
                return

        # Let other keys (typing) fall through to search or children
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):  # type: ignore[override]
        if isinstance(obj, LaunchButton) and self._handle_reorder_event(obj, event):
            return True
        if obj is self._search_edit and event.type() == QEvent.Type.KeyPress:
            if isinstance(event, QKeyEvent):
                if event.key() == Qt.Key.Key_Escape:
                    if self._search_edit.text():
                        self._search_edit.clear()
                        return True
                if event.key() == Qt.Key.Key_Down:
                    # From filter box, Down jumps into the list (first result)
                    vis = self._get_visible_launch_buttons()
                    if vis:
                        self._set_keyboard_current(vis[0])
                        # Move focus so further arrows stay in our keyPress path if needed
                        try:
                            vis[0].setFocus(Qt.FocusReason.OtherFocusReason)
                        except Exception:
                            pass
                        return True  # consume so it doesn't insert text
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    # Enter launches only a row the user has already moved to.
                    if self._current_button is not None and self._current_button.isVisible():
                        self._on_button_clicked(self._current_button.launcher)
                        return True
        return super().eventFilter(obj, event)
