"""Animated dropdown panel containing the launcher buttons.

Shown below the trigger on hover. Handles its own mouse tracking so the list
stays visible while the mouse travels from the arrow into the list.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import QCursor, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QScrollArea,
    QFrame,
    QLabel,
    QLineEdit,
    QMenu,
    QApplication,
    QPushButton,
)

from ..config import AppConfig, Launcher
from ..moves import container_token, launcher_token, merge_visible_order
from .launch_button import LaunchButton
from .stay_on_top import keep_menu_above_lists
from .theme import frame_qss, heading_qss, hint_qss, scroll_qss, search_qss
from .dropdown_drag import _DRAG_LIFT_X, DragReorderMixin
from .dropdown_motion import PanelMotionMixin
from .locked_pair import _HIDE_DECAY_MS, LockedPairMotion
from .rows import SubmenuButton, _RowGhost
import contextlib

# A list is allowed at least this tall before it scrolls, more when the screen has room.
_MIN_MAX_LIST_H = 420
# Kept clear between a full-height list and the edge of the screen.
_SCREEN_EDGE_GAP = 8

# Re-exported for callers that import these from here.
__all__ = [
    "DropdownPanel",
    "LockedPairMotion",
    "SubmenuButton",
    "merge_visible_order",
    "_DRAG_LIFT_X",
    "_HIDE_DECAY_MS",
]









class DropdownPanel(DragReorderMixin, PanelMotionMixin, QWidget):
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
    # Mixed main-list order. Tokens are "container:<id>" and "launcher:<id>".
    rows_reordered = Signal(list)
    # launcher id, source menu key, destination menu key, insertion index.
    # Index -1 appends. Emitted instead of reordered when the row changes menus.
    external_drop = Signal(str, str, str, int)
    drag_finished = Signal()
    # Execute-group rows. Emitted on hover when set_emit_row_hover is on.
    row_hovered = Signal(str)
    row_left = Signal(str)

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
        # Shared with the execute-groups list while arrow hover opens and closes both.
        self._locked_pair: LockedPairMotion | None = None
        self._linked_closing = False
        self._linked_full_h = 0
        self._linked_x = 0
        self._linked_edge = 0
        self._linked_grow_top = True
        self._linked_fraction = 1.0
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._do_hide)
        self._anchor_trigger: QWidget | None = None  # for re-positioning after show() on some platforms
        self._position_hook: Callable[[], None] | None = None
        self._grow_from_top: bool = True
        self._fixed_edge_y: int = 0

        # Keyboard navigation state
        self._current_button: LaunchButton | None = None
        self._visible_buttons: list[LaunchButton] = []  # subset of _buttons that are currently visible (post-filter)

        # Click-drag reorder. A short press still launches. A longer drag moves the row.
        self._drag_button: QPushButton | None = None
        self._drag_press = QPoint()
        self._drag_last_global = QPoint()
        self._drag_active = False
        self._drag_detached = False
        self._drag_order: list[QPushButton] = []
        self._drag_base_y = 0
        self._drag_home_x = 0
        self._drag_row_step = 0
        self._drag_row_h = 0
        self._row_anims: dict[QPushButton, QPropertyAnimation] = {}
        self._suppress_click = False
        # Main popup interleaves container rows with launchers. Other lists do not.
        self._mix_rows = False
        # "main", "groups", "container:<id>", or "execute:<id>". Empty skips cross-menu drops.
        self._drag_source_key = ""
        self._peer_at: Callable[[QPoint], DropdownPanel | None] | None = None
        self._emit_row_hover = False
        self._external_target: tuple[str, int] | None = None
        self._pre_drag_buttons: list | None = None
        self._pre_drag_tokens: list[str] = []
        self._ghost: _RowGhost | None = None
        self._app_filter = False
        self._in_drag_step = False
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
        self._frame.setStyleSheet(frame_qss())

        self._layout = QVBoxLayout(self._frame)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(3)

        self._heading = QLabel(self._frame)
        self._heading.setObjectName("listHeading")
        self._heading.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._heading.setStyleSheet(heading_qss())
        self._heading.hide()

        self.setAccessibleName("Launcher list")
        self._search_edit = QLineEdit(self._frame)
        self._search_edit.setPlaceholderText("Filter launchers...")
        self._search_edit.setAccessibleName("Filter launchers")
        self._search_edit.setStyleSheet(search_qss())
        self._search_edit.textChanged.connect(self._apply_filter)
        self._search_edit.installEventFilter(self)

        # Scroll area in case there are many items
        self._scroll = QScrollArea(self._frame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(scroll_qss())

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

    def _rest_opacity(self) -> float:
        """A list at rest is fully solid. The Opacity slider is for the arrow only;
        a list is only see-through while it fades in or out."""
        return 1.0

    def _decay_ms(self) -> int:
        """How long the close fade lasts. The Decay rate slider stores this."""
        value = getattr(self._config.settings, "decay_ms", _HIDE_DECAY_MS)
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = _HIDE_DECAY_MS
        return max(0, min(1000, value))

    def set_heading(self, text: str) -> None:
        """Small corner label above the rows. Empty text hides it."""
        self._heading.setText(text)
        self._heading.setVisible(bool(text))
        self.setAccessibleName(text or "Launcher list")
        if self.isVisible():
            self._update_height_for_content()

    def use_position_hook(self, hook: Callable[[], None] | None) -> None:
        """Replace the default beside-the-arrow placement. None restores it."""
        self._position_hook = hook

    def set_list_copy(self, *, placeholder: str, empty_hint: str) -> None:
        """Filter box placeholder and the text shown when the list is empty."""
        self._empty_hint = empty_hint
        self._search_edit.setPlaceholderText(placeholder)
        self._search_edit.setAccessibleName(placeholder.rstrip("."))

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

    def set_mix_rows(self, enabled: bool) -> None:
        """Drag container rows among the launchers and save one mixed order."""
        self._mix_rows = enabled

    def set_drag_source_key(self, key: str) -> None:
        """Menu key for this list. Empty, or 'groups', never starts a cross-menu move."""
        self._drag_source_key = key

    def set_peer_finder(self, finder: Callable[[QPoint], DropdownPanel | None] | None) -> None:
        """Panel under a global point while a row is dragged. None keeps drags inside this list."""
        self._peer_at = finder

    def set_emit_row_hover(self, enabled: bool) -> None:
        """Emit row_hovered and row_left for launcher rows. The groups list uses this."""
        self._emit_row_hover = enabled

    def is_dragging(self) -> bool:
        return self._drag_active

    def dragging_submenu(self) -> bool:
        """True while a container row, not a launcher, is the dragged row."""
        return self._drag_active and isinstance(self._drag_button, SubmenuButton)

    def launcher_button(self, launcher_id: str) -> LaunchButton | None:
        for button in self._launch_buttons():
            if button.launcher.id == launcher_id:
                return button
        return None

    def row_at(self, global_pos: QPoint) -> QPushButton | None:
        """Visible launcher or container row under this global point."""
        for button in self._buttons:
            if not isinstance(button, (LaunchButton, SubmenuButton)) or not button.isVisible():
                continue
            if button.rect().contains(button.mapFromGlobal(global_pos)):
                return button
        return None

    def row_tokens(self) -> list[str]:
        """Visible main-popup rows as container:<id> and launcher:<id> tokens."""
        tokens: list[str] = []
        for button in self._buttons:
            token = self._token_for(button)
            if token is not None and button.isVisible():
                tokens.append(token)
        return tokens

    def visible_launcher_ids(self) -> list[str]:
        return [button.launcher.id for button in self._launch_buttons() if button.isVisible()]

    def drop_target_at(self, global_pos: QPoint) -> tuple[str, int] | None:
        """Where a launcher dropped at this point would land.

        A group row joins that execute group (index -1 appends). A container row
        on the main list joins that container. Anywhere else on a launcher list
        inserts among the visible rows.
        """
        if not self.isVisible() or not self.rect().contains(self.mapFromGlobal(global_pos)):
            return None
        if self._drag_source_key == "groups":
            row = self.row_at(global_pos)
            if isinstance(row, LaunchButton):
                return (f"execute:{row.launcher.id}", -1)
            return None
        if self._drag_source_key == "main":
            row = self.row_at(global_pos)
            if isinstance(row, SubmenuButton):
                return (container_token(row.item_id), -1)
            return ("main", self._insertion_index(global_pos, launchers_only=False))
        if self._drag_source_key.startswith("container:") or self._drag_source_key.startswith("execute:"):
            return (self._drag_source_key, self._insertion_index(global_pos, launchers_only=True))
        return None

    def apply_token_order(self, tokens: list[str]) -> None:
        """Put the existing rows in this token order. Unknown tokens are skipped."""
        by_token: dict[str, QPushButton] = {}
        rest = []
        for button in self._buttons:
            token = self._token_for(button)
            if token is None:
                rest.append(button)
            else:
                by_token[token] = button
        ordered: list[QPushButton] = []
        used: set[str] = set()
        for token in tokens:
            button = by_token.get(token)
            if button is not None and token not in used:
                ordered.append(button)
                used.add(token)
        for token, button in by_token.items():
            if token not in used:
                ordered.append(button)
        self._relayout_buttons(ordered + rest)

    def _token_for(self, button) -> str | None:
        if isinstance(button, SubmenuButton):
            return container_token(button.item_id)
        if isinstance(button, LaunchButton):
            return launcher_token(button.launcher.id)
        return None

    def _insertion_index(self, global_pos: QPoint, *, launchers_only: bool) -> int:
        rows = []
        for button in self._buttons:
            if launchers_only and not isinstance(button, LaunchButton):
                continue
            if not launchers_only and not isinstance(button, (LaunchButton, SubmenuButton)):
                continue
            if button.isVisible():
                rows.append(button)
        y = global_pos.y()
        for index, button in enumerate(rows):
            center = button.mapToGlobal(QPoint(0, button.height() // 2)).y()
            if y < center:
                return index
        return len(rows)

    def set_row_tooltip(self, provider: Callable[[Launcher], str] | None) -> None:
        """Replace the default launch tooltip. Used by the group list."""
        self._row_tooltip = provider

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

    def apply_theme(self) -> None:
        """Restyle this list from the active color scheme. Open rows keep their state."""
        self._frame.setStyleSheet(frame_qss())
        self._heading.setStyleSheet(heading_qss())
        self._search_edit.setStyleSheet(search_qss())
        self._scroll.setStyleSheet(scroll_qss())
        for widget in self._buttons:
            restyle = getattr(widget, "apply_theme", None)
            if restyle is not None:
                restyle()
            elif isinstance(widget, QLabel):
                widget.setStyleSheet(hint_qss())
        if self._ghost is not None:
            self._ghost.apply_theme()

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
            button.installEventFilter(self)
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
            hint.setStyleSheet(hint_qss())
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
                if match:
                    self._visible_buttons.append(w)
                if was_visible and not match:
                    self.submenu_left.emit(w.item_id)
            elif isinstance(w, QLabel):
                # the empty hint label
                w.setVisible(q == "")

        self._update_height_for_content()
        if previous is not None and previous in self._visible_buttons and previous.isVisible():
            self._set_keyboard_current(previous)

    def _max_list_height(self) -> int:
        """How tall the list may grow before it scrolls: all the room on the
        roomier side of the arrow, and never less than the old fixed limit.

        A fixed 420 px made a list that needed a few pixels more scroll by
        those few pixels, with a scrollbar appearing once it opened."""
        trigger = self._anchor_trigger
        if trigger is None:
            return _MIN_MAX_LIST_H
        top_left = trigger.mapToGlobal(QPoint(0, 0))
        screen = QApplication.screenAt(top_left) or QApplication.primaryScreen()
        if screen is None:
            return _MIN_MAX_LIST_H
        avail = screen.availableGeometry()
        above = top_left.y() - avail.top()
        below = avail.bottom() + 1 - (top_left.y() + trigger.size().height())
        return max(_MIN_MAX_LIST_H, max(above, below) - _SCREEN_EDGE_GAP)

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
                except RuntimeError:  # row already deleted
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
        target_h = min(target_h, self._max_list_height())
        self._frame.setFixedHeight(target_h)
        self.setFixedHeight(target_h)

        # The rows need their full height inside the scroll area. The scroll area
        # itself must stay shorter than that content, or the list clips at the
        # frame and the scrollbar never appears.
        self._button_container.setMinimumHeight(inner_h)
        self._scroll.setMinimumHeight(0)

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

    def _show_item_menu(self, button: LaunchButton, pos: QPoint) -> None:
        """Right-click menu for one row. Edit and Delete only."""
        if self._drag_active:
            return
        previous = self._item_menu
        if previous is not None:
            with contextlib.suppress(RuntimeError):
                previous.aboutToHide.disconnect(self._on_item_menu_hidden)
            previous.close()

        launcher = button.launcher
        menu = QMenu(self)
        keep_menu_above_lists(menu)
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
            with contextlib.suppress(RuntimeError):
                previous.aboutToHide.disconnect(self._on_item_menu_hidden)
            previous.close()

        item_id = button.item_id
        menu = QMenu(self)
        keep_menu_above_lists(menu)
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
            with contextlib.suppress(RuntimeError):  # row already deleted
                self._current_button.set_keyboard_selected(False)
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
            with contextlib.suppress(RuntimeError):  # row already deleted
                self._scroll.ensureWidgetVisible(btn)

    def _get_visible_launch_buttons(self) -> list[LaunchButton | SubmenuButton]:
        """Return currently visible keyboard-navigable rows (launchers and containers)."""
        # Prefer the maintained list; fall back to live scan if needed
        if self._visible_buttons:
            return [b for b in self._visible_buttons if b.isVisible()]
        return [b for b in self._buttons if isinstance(b, (LaunchButton, SubmenuButton)) and b.isVisible()]

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

        Sets internal flags (_grow_from_top, _fixed_edge_y) so that
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
            # The line just below the list. QRect.bottom() is its last row of
            # pixels, one short of that, which left the list a pixel too high.
            fixed_edge_y = final_rect.bottom() + 1
            grow_from_top = False

        # Store for animations so they expand/contract away from the edge.
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
        # An arrow wider than the launcher list would sit over this list's
        # top corner. Step out past the arrow instead.
        arrow = QRect(trig_pos, trigger.size())
        if rect.intersects(arrow):
            if place_left:
                rect.moveRight(min(rect.right(), arrow.left() - gap - 1))
            else:
                rect.moveLeft(max(rect.left(), arrow.right() + 1 + gap))
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
        self._fixed_edge_y = rect.top() if grow_from_top else rect.bottom() + 1

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
            x = host_geo.right() + gap if on_right else host_geo.left() - gap - target_w
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
        self._fixed_edge_y = rect.top() if self._grow_from_top else rect.bottom() + 1

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
                   Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Right):
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
            if (
                key == Qt.Key.Key_Right
                and isinstance(self._current_button, SubmenuButton)
                and self._current_button.isVisible()
            ):
                self.submenu_hovered.emit(self._current_button.item_id)
                event.accept()
                return
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._current_button is not None and self._current_button.isVisible():
                    if isinstance(self._current_button, SubmenuButton):
                        self.submenu_hovered.emit(self._current_button.item_id)
                    else:
                        # Emit launch for the keyboard-chosen item
                        self._on_button_clicked(self._current_button.launcher)
                event.accept()
                return

        # Let other keys (typing) fall through to search or children
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):  # type: ignore[override]
        # Follow the pointer after another window takes the mouse grab.
        if (
            self._drag_active
            and obj is not self._drag_button
            and isinstance(event, QMouseEvent)
        ):
            if event.type() == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton:
                self._drag_step(event.globalPosition().toPoint())
                return False
            if (
                event.type() == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton
            ):
                self._finish_drag(event.globalPosition().toPoint())
                return False
        if self._emit_row_hover and not self._drag_active and isinstance(obj, LaunchButton):
            if event.type() == QEvent.Type.Enter:
                self.row_hovered.emit(obj.launcher.id)
            elif event.type() == QEvent.Type.Leave:
                self.row_left.emit(obj.launcher.id)
        if isinstance(obj, (LaunchButton, SubmenuButton)) and self._handle_reorder_event(obj, event):
            return True
        if obj is self._search_edit and event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            if event.key() == Qt.Key.Key_Escape and self._search_edit.text():
                self._search_edit.clear()
                return True
            if event.key() == Qt.Key.Key_Down:
                # From filter box, Down jumps into the list (first result)
                vis = self._get_visible_launch_buttons()
                if vis:
                    self._set_keyboard_current(vis[0])
                    # Move focus so further arrows stay in our keyPress path if needed
                    with contextlib.suppress(RuntimeError):  # row already deleted
                        vis[0].setFocus(Qt.FocusReason.OtherFocusReason)
                    return True  # consume so it doesn't insert text
            if (
                event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and self._current_button is not None
                and self._current_button.isVisible()
            ):
                # Enter launches or opens only a row the user has already moved to.
                if isinstance(self._current_button, SubmenuButton):
                    self.submenu_hovered.emit(self._current_button.item_id)
                else:
                    self._on_button_clicked(self._current_button.launcher)
                return True
        return super().eventFilter(obj, event)
