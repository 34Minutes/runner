"""Wires the arrow, the lists, the dialogs, and the tray together.

There are four lists:

- the main popup (launchers and container rows),
- the execute-groups list,
- a container's launchers, beside its row in the main popup,
- an execute group's launchers, beside its row in the execute-groups list.

The execute-groups list is shown in one of two ways, which is PopupMode.
In MAIN it sits beside the main popup when Show execute groups is on. In
GROUPS_ONLY it was opened on its own from the arrow menu and the main popup
is hidden.

The two side lists are SideMenus. Each one is open for at most one row,
and it fades out a moment after the pointer leaves both it and that row.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from enum import Enum, auto

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QCursor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon, QWidget

from .config import (
    DEFAULT_TRIGGER_HEIGHT,
    DEFAULT_TRIGGER_WIDTH,
    ConfigManager,
    ContainerGroup,
    Group,
    Launcher,
)
from .elevation import warn_if_elevated
from .groups import GROUP_STEP_GAP_MS, execution_steps, run_group_steps
from .launcher import launch
from .moves import member_launchers, visible_main_tokens
from .ui.add_dialog import AddEditDialog
from .ui.container_dialog import ContainerDialog
from .ui.container_manager import ContainerManagerDialog
from .ui.dropdown import DropdownPanel, LockedPairMotion, SubmenuButton
from .ui.greeting import StartupGreeting, clamp_trigger_to_screen, ensure_visible_trigger_size
from .ui.group_dialog import GroupDialog
from .ui.group_manager import GroupManagerDialog
from .ui.launch_button import LaunchButton
from .ui.manager_dialog import ManagerDialog
from .ui.stay_on_top import question as stay_on_top_question
from .ui.stay_on_top import warning as stay_on_top_warning
from .ui.theme import current, use
from .ui.trigger import TriggerWidget, clamp_decay_ms, clamp_opacity_percent

if sys.platform == "win32":
    from .utils import windows as win_utils  # type: ignore
else:
    win_utils = None  # type: ignore

DEFAULT_POSITION = (100, 100)
# A slider writes the config this long after it stops moving.
SLIDER_SAVE_DELAY_MS = 400
# Shown at most this many config problems in the warning. The rest are counted.
_MAX_PROBLEMS_SHOWN = 12


class PopupMode(Enum):
    MAIN = auto()  # The main popup, with execute groups beside it when that switch is on.
    GROUPS_ONLY = auto()  # The execute-groups list on its own, from the arrow menu.


def _pointer_over(widget: QWidget) -> bool:
    return widget.isVisible() and widget.frameGeometry().contains(QCursor.pos())


def _decay(panel: DropdownPanel) -> None:
    """Fade a side list out in place. An instant hide is too fast to move onto."""
    if panel.isVisible() and not panel.is_closing():
        panel.start_hide_animation()


class SideMenu:
    """A list that opens beside one row of another list."""

    HIDE_DELAY_MS = 180

    def __init__(self, panel: DropdownPanel, anchor_for: Callable[[str], QWidget | None]) -> None:
        self.panel = panel
        self._anchor_for = anchor_for
        self.open_id: str | None = None
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(self.HIDE_DELAY_MS)
        self.timer.timeout.connect(self.hide_if_left)

    def anchor(self) -> QWidget | None:
        """The row this list is open for, when it is on screen."""
        if not self.open_id:
            return None
        button = self._anchor_for(self.open_id)
        if button is None or not button.isVisible():
            return None
        return button

    def is_open_for(self, item_id: str) -> bool:
        return (
            self.open_id == item_id
            and self.panel.isVisible()
            and not self.panel.is_closing()
        )

    def hide(self) -> None:
        self.timer.stop()
        self.open_id = None
        self.panel.use_position_hook(None)
        if self.panel.isVisible():
            self.panel.force_hide()

    def schedule_hide(self) -> None:
        if self.open_id:
            self.timer.start()

    def on_row_left(self, item_id: str) -> None:
        if item_id == self.open_id:
            self.schedule_hide()

    def hide_if_left(self) -> None:
        if _pointer_over(self.panel):
            return
        button = self.anchor()
        if button is not None and button.rect().contains(button.mapFromGlobal(QCursor.pos())):
            return
        _decay(self.panel)


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
        ("Add new launcher...", on_add),
        ("Manage launchers...", on_manage),
        ("Reset position & size", on_reset),
        ("Reload config", on_reload),
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


def fill_main_dropdown(dropdown: DropdownPanel, cfg: ConfigManager) -> None:
    """Launcher rows and container rows, in the saved mixed order."""
    dropdown.set_submenu_items(
        [(group.id, group.name) for group in cfg.config.container_groups]
    )
    dropdown.rebuild_buttons(cfg.get_main_view_launchers())
    dropdown.apply_token_order(visible_main_tokens(cfg.config))


class RunnerController:
    """Owns the widgets and keeps them in step with the config."""

    def __init__(self, app: QApplication, cfg: ConfigManager) -> None:
        self.app = app
        self.cfg = cfg
        self.mode = PopupMode.MAIN

        self._build_widgets()
        self._place_trigger_on_start()
        self._build_timers()
        self._connect_hover()
        self._connect_lists()
        self._connect_trigger_menu()
        self._connect_windows_startup()
        self._connect_geometry()

        self.tray = create_tray(
            on_add=self.show_add_dialog,
            on_manage=self.show_manager_dialog,
            on_reset=self.reset_position_and_size,
            on_reload=self.reload_config,
            on_exit=self.app.quit,
            on_click=self._on_tray_clicked,
        )
        self._apply_opacity()

    # ------------------------------------------------------------------ setup

    @property
    def settings(self):
        return self.cfg.config.settings

    def _build_widgets(self) -> None:
        cfg = self.cfg
        self.trigger = TriggerWidget(cfg.config)
        self.dropdown = DropdownPanel(cfg.config)
        self.group_panel = DropdownPanel(cfg.config, honor_pin=False)
        self.container_panel = DropdownPanel(cfg.config, honor_pin=False)
        self.execute_panel = DropdownPanel(cfg.config, honor_pin=False)

        self.dropdown.set_mix_rows(True)
        self.dropdown.set_drag_source_key("main")

        self.group_panel.set_list_copy(placeholder="Filter execute groups...", empty_hint="")
        self.group_panel.set_order_ids(lambda: [group.id for group in self.cfg.config.groups])
        self.group_panel.set_row_tooltip(self._group_row_tooltip)
        self.group_panel.set_heading("Execute Groups")
        self.group_panel.set_drag_source_key("groups")
        self.group_panel.set_emit_row_hover(True)

        self.container_panel.set_list_copy(
            placeholder="Filter launchers...", empty_hint="Nothing in this container."
        )
        self.execute_panel.set_list_copy(
            placeholder="Filter launchers...", empty_hint="Nothing in this execute group."
        )

        self.container_menu = SideMenu(self.container_panel, self.dropdown.submenu_button)
        self.execute_menu = SideMenu(self.execute_panel, self.group_panel.launcher_button)
        self.container_panel.set_order_ids(
            lambda: self._member_ids(self._container_by_id(self.container_menu.open_id))
        )
        self.execute_panel.set_order_ids(
            lambda: self._member_ids(self._group_by_id(self.execute_menu.open_id))
        )

        # Arrow hover with Show execute groups on opens and closes the main
        # popup and the groups list on one clock, so they fade together.
        self.locked_pair = LockedPairMotion(
            self.dropdown,
            lambda: self.settings.animation_duration_ms,
            hide_duration_ms=lambda: clamp_decay_ms(self.settings.decay_ms),
        )
        self.dropdown.set_locked_pair(self.locked_pair)
        self.group_panel.set_locked_pair(self.locked_pair)

        self.greeting = StartupGreeting()
        fill_main_dropdown(self.dropdown, cfg)

    def _place_trigger_on_start(self) -> None:
        # First launch on this machine uses the large default arrow. Later
        # launches keep the size and position already stored in the config.
        if not self.cfg.had_saved_config:
            ensure_visible_trigger_size(self.cfg, self.trigger)
        self._reset_if_off_screen()
        if clamp_trigger_to_screen(self.trigger):
            self.cfg.update_settings(position_x=self.trigger.x(), position_y=self.trigger.y())
        self.dropdown.refresh_filter_visibility()

    def _build_timers(self) -> None:
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(self.settings.hover_delay_ms)
        self.hide_timer.timeout.connect(self._do_hide)
        # One config write after a slider stops moving, not one per tick.
        self.save_timer = QTimer()
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(SLIDER_SAVE_DELAY_MS)
        self.save_timer.timeout.connect(self.cfg.save)

    def _connect_hover(self) -> None:
        self.trigger.hover_enter.connect(self._on_trigger_enter)
        self.trigger.hover_leave.connect(self._on_trigger_leave)
        self.dropdown.hover_enter.connect(self._on_dropdown_enter)
        self.dropdown.hover_leave.connect(self._on_dropdown_leave)
        self.group_panel.hover_enter.connect(self._on_group_enter)
        self.group_panel.hover_leave.connect(self._on_group_leave)
        self.group_panel.closed.connect(self._on_group_panel_closed)
        self.container_panel.hover_enter.connect(lambda: self._on_side_enter(self.container_menu))
        self.container_panel.hover_leave.connect(self._on_container_leave)
        self.execute_panel.hover_enter.connect(lambda: self._on_side_enter(self.execute_menu))
        self.execute_panel.hover_leave.connect(self._on_execute_leave)
        self.dropdown.submenu_hovered.connect(self._show_container_menu)
        self.dropdown.submenu_left.connect(self.container_menu.on_row_left)
        self.group_panel.row_hovered.connect(self._show_execute_members)
        self.group_panel.row_left.connect(self.execute_menu.on_row_left)

    def _connect_lists(self) -> None:
        dropdown, container, execute, groups = (
            self.dropdown,
            self.container_panel,
            self.execute_panel,
            self.group_panel,
        )
        for panel in (dropdown, container, execute):
            panel.set_peer_finder(self._find_drop_peer)
            panel.launch_requested.connect(self._on_launch)
            panel.edit_requested.connect(self._on_edit_launcher)
            panel.delete_requested.connect(self._on_delete_launcher)
            panel.external_drop.connect(self._on_external_drop)
        for panel in (dropdown, container, execute, groups):
            panel.drag_finished.connect(self._on_drag_finished)

        dropdown.rows_reordered.connect(self.cfg.apply_main_row_order)
        dropdown.submenu_edit_requested.connect(self._on_container_edit)
        dropdown.submenu_delete_requested.connect(self._on_container_delete)
        container.reordered.connect(self._on_container_reordered)
        execute.reordered.connect(self._on_execute_members_reordered)

        groups.launch_requested.connect(self._on_group_launch)
        groups.edit_requested.connect(self._on_group_edit)
        groups.delete_requested.connect(self._on_group_delete)
        groups.reordered.connect(self.cfg.reorder_groups)

    def _connect_trigger_menu(self) -> None:
        trigger = self.trigger
        trigger.request_add.connect(lambda: self.show_add_dialog())
        trigger.request_manage.connect(self.show_manager_dialog)
        trigger.request_reset.connect(self.reset_position_and_size)
        trigger.request_exit.connect(self.app.quit)
        trigger.request_add_group.connect(lambda: self.show_group_dialog())
        trigger.request_manage_groups.connect(self.show_group_manager)
        trigger.request_groups.connect(self._show_group_panel)
        trigger.request_containers.connect(self._show_main_popup)
        trigger.request_add_container.connect(lambda: self.show_container_dialog())
        trigger.request_manage_containers.connect(self.show_container_manager)

        trigger.pin_toggled.connect(self._on_pin_toggled)
        trigger.filter_toggled.connect(self._on_filter_toggled)
        trigger.greeting_toggled.connect(self._on_greeting_toggled)
        trigger.groups_toggled.connect(self._on_show_groups_toggled)
        # Sliders apply every tick but write the file once they settle.
        trigger.window_opacity_changed.connect(self._on_opacity_changed)
        trigger.decay_changed.connect(
            lambda ms: self._update_settings_soon(decay_ms=clamp_decay_ms(ms))
        )
        trigger.color_scheme_selected.connect(self._on_color_scheme)

    def _connect_windows_startup(self) -> None:
        if sys.platform != "win32" or win_utils is None:
            return
        # Recreate the Run entry on each start, in case Runner.exe was moved.
        if self.settings.launch_at_startup:
            win_utils.ensure_startup_entry(True)

        def on_startup_toggled(checked: bool) -> None:
            self.cfg.update_settings(launch_at_startup=checked)
            if not win_utils.ensure_startup_entry(checked):
                stay_on_top_warning(
                    self.trigger,
                    "Launch at Windows startup",
                    "Windows did not allow Runner to "
                    + ("add itself to" if checked else "remove itself from")
                    + " the startup list.",
                )

        self.trigger.startup_toggled.connect(on_startup_toggled)

    def _connect_geometry(self) -> None:
        # The lists follow the arrow while it moves. The position is saved once, on release.
        self.trigger.dragged.connect(lambda _x, _y: self._follow_trigger())
        self.trigger.position_changed.connect(self._save_position)
        self.trigger.size_changed.connect(self._save_size)
        self.app.aboutToQuit.connect(self._save_trigger_geometry)
        self.app.aboutToQuit.connect(self.flush_pending_save)

    def start(self) -> None:
        """Show the arrow. Positioning waits until the window is realized."""
        self.trigger.show()
        self.trigger.raise_()
        QTimer.singleShot(0, self._after_show)

    def _after_show(self) -> None:
        if warn_if_elevated(self.trigger, self.app.quit):
            return  # the user chose to quit
        if self.settings.show_startup_greeting:
            self.greeting.present(self.trigger)
        self._apply_pinned_state()
        self._report_load_problems()

    # ------------------------------------------------------------ lookups

    def _group_by_id(self, group_id: str | None) -> Group | None:
        return next((g for g in self.cfg.config.groups if g.id == group_id), None)

    def _container_by_id(self, group_id: str | None) -> ContainerGroup | None:
        return next((g for g in self.cfg.config.container_groups if g.id == group_id), None)

    @staticmethod
    def _member_ids(group: Group | ContainerGroup | None) -> list[str]:
        return [member.launcher_id for member in group.members] if group else []

    def _group_row_tooltip(self, row: Launcher) -> str:
        lines = [f"Run execute group: {row.name}"]
        group = self._group_by_id(row.id)
        if group is not None and group.show_contents:
            lines.append("Hover to see its launchers")
        lines.append("Drag up or down to reorder")
        lines.append("Right-click to edit or delete")
        return "\n".join(lines)

    def _groups_beside_enabled(self) -> bool:
        return bool(self.settings.show_groups)

    def _groups_only(self) -> bool:
        return self.mode is PopupMode.GROUPS_ONLY

    def _pointer_over_any(self, *, trigger: bool = True) -> bool:
        panels = [self.dropdown, self.group_panel, self.container_panel, self.execute_panel]
        if trigger:
            panels.append(self.trigger)
        return any(_pointer_over(widget) for widget in panels)

    def _any_drag(self) -> bool:
        return any(
            panel.is_dragging()
            for panel in (self.dropdown, self.group_panel, self.container_panel, self.execute_panel)
        )

    def _keep_arrow_on_top(self, *panels: DropdownPanel) -> None:
        """The arrow stays above the lists that open from it."""
        self.trigger.raise_()
        for panel in panels:
            panel.stackUnder(self.trigger)

    # -------------------------------------------------------------- hiding

    def _schedule_hide(self) -> None:
        self.hide_timer.start()

    def _cancel_hide(self) -> None:
        self.hide_timer.stop()
        for panel in (self.dropdown, self.group_panel, self.container_panel, self.execute_panel):
            panel.cancel_hide()

    def _should_hide_on_leave(self) -> bool:
        return self._groups_only() or not self.settings.pinned_open

    def _collapse_open_lists(self) -> None:
        """Close every open list now.

        A fade stays under the pointer, and the hover that is already there
        cancels it. That happens when the launched app was already focused,
        so the pointer never leaves. A selection hides the lists outright.
        """
        if self.settings.pinned_open:
            return
        self.container_menu.hide()
        self.execute_menu.hide()
        if self.dropdown.isVisible():
            self.dropdown.force_hide()
        if self.group_panel.isVisible():
            self.group_panel.force_hide()

    def _do_hide(self) -> None:
        if self._pointer_over_any():
            return
        _decay(self.container_panel)
        _decay(self.execute_panel)
        if self._groups_only():
            self.group_panel.start_hide_animation()
            return
        pinned = self.settings.pinned_open
        if (
            not pinned
            and self._groups_beside_enabled()
            and self.locked_pair.close_visible([self.dropdown, self.group_panel])
        ):
            return
        if self.group_panel.isVisible():
            self.group_panel.start_hide_animation()
        if not pinned:
            self.dropdown.start_hide_animation()

    # ---------------------------------------------------- groups list beside

    def _refresh_group_list(self) -> None:
        rows = [
            Launcher(id=group.id, name=group.name, command="")
            for group in self.cfg.config.groups
        ]
        self.group_panel.rebuild_buttons(rows)
        if self.group_panel.isVisible():
            self.group_panel.update_height_for_content()

    def _place_groups_beside(self) -> None:
        self.group_panel.position_beside(self.dropdown, self.trigger)

    def _show_groups_beside(self) -> None:
        """The launcher list stays. Groups sit beside it, toward the middle of the screen.

        An empty group list stays hidden.
        """
        if self._groups_only() or not self._groups_beside_enabled():
            return
        if not self.cfg.config.groups:
            self._hide_groups_beside()
            return
        self._refresh_group_list()
        self.group_panel.use_position_hook(self._place_groups_beside)
        if self.locked_pair.is_presented():
            self.locked_pair.reposition([self.dropdown, self.group_panel])
        elif self.group_panel.isVisible():
            self.group_panel.ensure_visible_and_sized()
        else:
            self.group_panel.start_show_animation()
        self._keep_arrow_on_top(self.dropdown, self.group_panel)

    def _hide_groups_beside(self) -> None:
        if self._groups_only():
            return
        self.group_panel.use_position_hook(None)
        if self.group_panel.isVisible():
            self.group_panel.force_hide()

    def _show_group_panel(self) -> None:
        """The execute-groups list on its own, from the arrow menu."""
        self.container_menu.hide()
        self.execute_menu.hide()
        if not self.cfg.config.groups:
            self.mode = PopupMode.MAIN
            self._hide_groups_beside()
            return
        self.mode = PopupMode.GROUPS_ONLY
        self._cancel_hide()
        self.group_panel.use_position_hook(None)
        if self.dropdown.isVisible():
            self.dropdown.force_hide()
        self._refresh_group_list()
        self.group_panel.position_adjacent(self.trigger)
        if self.group_panel.isVisible():
            self.group_panel.ensure_visible_and_sized()
        else:
            self.group_panel.start_show_animation()
        self._keep_arrow_on_top(self.group_panel)

    def _on_group_panel_closed(self) -> None:
        # A hide that was already running can finish after the list is shown again.
        if self.group_panel.isVisible():
            return
        self.mode = PopupMode.MAIN
        if self.settings.pinned_open:
            self._apply_pinned_state()

    # ---------------------------------------------------------- main popup

    def _dropdown_settled_open(self) -> bool:
        """True when the launcher list is already fully open on its own."""
        return (
            self.dropdown.isVisible()
            and not self.dropdown.is_closing()
            and self.dropdown.windowOpacity() >= 0.95
            and not self.locked_pair.is_presented()
        )

    def _show_main_popup(self) -> None:
        """Open the launcher list, where container group rows live.

        Arrow hover with execute groups showing drives both lists from one
        clock. A list that is already fully open, such as while pinned, stays
        put instead of collapsing back to the start of that clock.
        """
        self.mode = PopupMode.MAIN
        self._cancel_hide()
        self.container_menu.hide()
        self.execute_menu.hide()
        fill_main_dropdown(self.dropdown, self.cfg)
        self.dropdown.position_adjacent(self.trigger)
        groups_too = self._groups_beside_enabled() and bool(self.cfg.config.groups)
        if groups_too and (self.locked_pair.is_presented() or not self._dropdown_settled_open()):
            self._refresh_group_list()
            self.group_panel.use_position_hook(self._place_groups_beside)
            self.locked_pair.open([self.dropdown, self.group_panel])
        else:
            if not self.dropdown.isVisible() or self.dropdown.is_closing():
                self.dropdown.start_show_animation()
            if groups_too:
                self._show_groups_beside()
            else:
                self._hide_groups_beside()
        self._keep_arrow_on_top(self.dropdown, self.group_panel)

    def _apply_pinned_state(self) -> None:
        if self._groups_only():
            return
        if self.settings.pinned_open:
            self.dropdown.position_adjacent(self.trigger)
            self.dropdown.cancel_hide()
            self.dropdown.update_height_for_content()
            if not self.dropdown.isVisible():
                self.dropdown.start_show_animation()
            else:
                self.dropdown.update_height_for_content()
            self._keep_arrow_on_top(self.dropdown)
            if self._groups_beside_enabled():
                self._show_groups_beside()
        else:
            self.dropdown.force_hide()
            self.container_menu.hide()
            self.execute_menu.hide()
            self._hide_groups_beside()

    def _follow_trigger(self) -> None:
        """Keep whichever list is open beside the arrow."""
        if self._groups_only() and self.group_panel.isVisible():
            self.group_panel.use_position_hook(None)
            self.group_panel.position_adjacent(self.trigger)
            self.group_panel.ensure_visible_and_sized()
            self._keep_arrow_on_top(self.group_panel)
            return
        if self.locked_pair.is_presented():
            if self._groups_beside_enabled() and self.cfg.config.groups:
                self._show_groups_beside()
            self._keep_arrow_on_top(self.dropdown, self.group_panel)
            return
        pinned = self.settings.pinned_open
        if not self.dropdown.isVisible() and not pinned:
            return
        self.dropdown.position_adjacent(self.trigger)
        if pinned:
            self.dropdown.ensure_visible_and_sized()
        self._keep_arrow_on_top(self.dropdown)
        if self._groups_beside_enabled() and (self.group_panel.isVisible() or pinned):
            self._show_groups_beside()

    # ------------------------------------------------------- hover handlers

    def _on_trigger_enter(self) -> None:
        self._cancel_hide()
        self.container_menu.hide()
        self.execute_menu.hide()
        if self._groups_only():
            self.group_panel.position_adjacent(self.trigger)
            if self.group_panel.is_closing() or not self.group_panel.isVisible():
                self._show_group_panel()
            self._keep_arrow_on_top(self.group_panel)
            return
        self._show_main_popup()

    def _on_trigger_leave(self) -> None:
        # Moving from the arrow onto a list must not start a hide.
        # The list's own leave collapses it.
        if self._pointer_over_any(trigger=False):
            return
        if self._should_hide_on_leave():
            self._schedule_hide()

    def _on_dropdown_enter(self) -> None:
        self._cancel_hide()
        if self.dropdown.is_closing():
            self.dropdown.cancel_close()

    def _on_dropdown_leave(self) -> None:
        if (
            _pointer_over(self.group_panel)
            or _pointer_over(self.container_panel)
            or _pointer_over(self.execute_panel)
        ):
            return
        self.container_menu.schedule_hide()
        if not self.settings.pinned_open:
            self._schedule_hide()

    def _on_group_enter(self) -> None:
        self._cancel_hide()
        self.execute_menu.timer.stop()
        if self.group_panel.is_closing() and (
            self._groups_only() or self._groups_beside_enabled()
        ):
            self.group_panel.cancel_close()

    def _on_group_leave(self) -> None:
        if _pointer_over(self.execute_panel):
            return
        self.execute_menu.schedule_hide()
        if self._groups_only() or (
            self._groups_beside_enabled() and not self.settings.pinned_open
        ):
            self._schedule_hide()

    def _on_side_enter(self, menu: SideMenu) -> None:
        self._cancel_hide()
        menu.timer.stop()
        if menu.panel.is_closing():
            menu.panel.cancel_close()

    def _on_container_leave(self) -> None:
        self.container_menu.schedule_hide()
        if (
            _pointer_over(self.dropdown)
            or _pointer_over(self.trigger)
            or _pointer_over(self.execute_panel)
        ):
            return
        if self._should_hide_on_leave():
            self._schedule_hide()

    def _on_execute_leave(self) -> None:
        self.execute_menu.schedule_hide()
        if (
            _pointer_over(self.group_panel)
            or _pointer_over(self.dropdown)
            or _pointer_over(self.trigger)
            or _pointer_over(self.container_panel)
        ):
            return
        if self._should_hide_on_leave():
            self._schedule_hide()

    # ------------------------------------------------------------ side menus

    def _container_prefer_right(self) -> bool:
        """Open on the side opposite the execute-groups list when that list is up."""
        return not (self.group_panel.isVisible() and self.group_panel.x() >= self.dropdown.x())

    def _execute_prefer_right(self) -> bool:
        """Open away from the main list when both lists are on screen."""
        return not (self.dropdown.isVisible() and self.dropdown.x() >= self.group_panel.x())

    def _place_container(self) -> None:
        button = self.container_menu.anchor()
        if button is not None:
            self.container_panel.position_next_to(
                self.dropdown, button, prefer_right=self._container_prefer_right()
            )

    def _place_execute_members(self) -> None:
        button = self.execute_menu.anchor()
        if button is not None:
            self.execute_panel.position_next_to(
                self.group_panel, button, prefer_right=self._execute_prefer_right()
            )

    def _show_container_menu(self, group_id: str, *, force: bool = False) -> None:
        menu, panel = self.container_menu, self.container_panel
        # This panel is the source while a launcher is dragged out of it.
        if panel.is_dragging():
            return
        group = self._container_by_id(group_id)
        button = self.dropdown.submenu_button(group_id) if group is not None else None
        if not self.dropdown.isVisible() or button is None or not button.isVisible():
            menu.hide()
            return
        menu.timer.stop()
        already = not force and menu.is_open_for(group_id)
        menu.open_id = group_id
        panel.set_drag_source_key(f"container:{group_id}")
        panel.set_heading(group.name)
        panel.use_position_hook(self._place_container)
        panel.cancel_hide()
        if already:
            return
        panel.rebuild_buttons(member_launchers(group.members, self.cfg.config.launchers))
        if panel.isVisible() and not panel.is_closing():
            panel.ensure_visible_and_sized()
        else:
            panel.start_show_animation(focus=not self._any_drag())
        self._keep_arrow_on_top(self.dropdown, panel)

    def _show_execute_members(self, group_id: str, *, force: bool = False) -> None:
        menu, panel = self.execute_menu, self.execute_panel
        if panel.is_dragging() or self.group_panel.is_dragging():
            return
        group = self._group_by_id(group_id)
        if group is None or not self.group_panel.isVisible():
            menu.hide()
            return
        # Show group contents defaults off. Hover and drag-over stay collapsed.
        if not group.show_contents:
            if menu.open_id is not None:
                menu.hide()
            return
        button = self.group_panel.launcher_button(group_id)
        if button is None or not button.isVisible():
            menu.hide()
            return
        menu.timer.stop()
        already = not force and menu.is_open_for(group_id)
        menu.open_id = group_id
        panel.set_drag_source_key(f"execute:{group_id}")
        panel.set_heading(group.name)
        panel.use_position_hook(self._place_execute_members)
        panel.cancel_hide()
        if already:
            return
        panel.rebuild_buttons(member_launchers(group.members, self.cfg.config.launchers))
        if panel.isVisible() and not panel.is_closing():
            panel.ensure_visible_and_sized()
        else:
            panel.start_show_animation(focus=not self._any_drag())
        self._keep_arrow_on_top(self.group_panel, panel)

    def _refresh_open_container(self) -> None:
        if self.container_menu.open_id and self.container_panel.isVisible():
            self._show_container_menu(self.container_menu.open_id, force=True)

    def _refresh_open_execute(self) -> None:
        if self.execute_menu.open_id and self.execute_panel.isVisible():
            self._show_execute_members(self.execute_menu.open_id, force=True)

    def _refresh_open_list(self) -> None:
        fill_main_dropdown(self.dropdown, self.cfg)
        self._refresh_open_container()
        self._refresh_open_execute()
        if self.settings.pinned_open:
            self._apply_pinned_state()

    def _sync_groups_after_change(self) -> None:
        """Keep an open groups list in step with add, edit, and delete.

        The member list closes when its execute group is gone. With no groups
        left, the list hides.
        """
        if self.execute_menu.open_id and self._group_by_id(self.execute_menu.open_id) is None:
            self.execute_menu.hide()
        elif self.execute_menu.open_id:
            self._refresh_open_execute()
        if self._groups_only():
            if not self.cfg.config.groups:
                self.group_panel.force_hide()
                return
            self._refresh_group_list()
            if self.group_panel.isVisible():
                self.group_panel.position_adjacent(self.trigger)
                self.group_panel.ensure_visible_and_sized()
            return
        if self._groups_beside_enabled() and (
            self.group_panel.isVisible()
            or self.dropdown.isVisible()
            or self.settings.pinned_open
        ):
            self._show_groups_beside()

    # ------------------------------------------------------------- dragging

    def _find_drop_peer(self, global_pos: QPoint) -> DropdownPanel | None:
        """Open the menu under the pointer, then return the list that contains it."""
        source = next(
            (
                panel
                for panel in (
                    self.dropdown,
                    self.container_panel,
                    self.execute_panel,
                    self.group_panel,
                )
                if panel.is_dragging()
            ),
            None,
        )
        self._cancel_hide()
        self.container_menu.timer.stop()
        self.execute_menu.timer.stop()
        # A container row only reorders inside the main list.
        if source is self.dropdown and source.dragging_submenu():
            if self.dropdown.isVisible() and self.dropdown.frameGeometry().contains(global_pos):
                return self.dropdown
            return None
        if (
            source is not self.execute_panel
            and self.group_panel.isVisible()
            and not self.group_panel.is_dragging()
        ):
            row = self.group_panel.row_at(global_pos)
            if isinstance(row, LaunchButton):
                self._show_execute_members(row.launcher.id)
        if source is not self.container_panel and self.dropdown.isVisible():
            row = self.dropdown.row_at(global_pos)
            if isinstance(row, SubmenuButton):
                self._show_container_menu(row.item_id)
        for panel in (self.execute_panel, self.container_panel, self.dropdown, self.group_panel):
            if panel.isVisible() and panel.frameGeometry().contains(global_pos):
                return panel
        return None

    def _dest_visible(self, target_key: str) -> list[str] | None:
        if target_key == "main":
            return self.dropdown.row_tokens()
        kind, _, ident = target_key.partition(":")
        if (
            kind == "container"
            and self.container_menu.open_id == ident
            and self.container_panel.isVisible()
        ):
            return self.container_panel.visible_launcher_ids()
        if (
            kind == "execute"
            and self.execute_menu.open_id == ident
            and self.execute_panel.isVisible()
        ):
            return self.execute_panel.visible_launcher_ids()
        return None

    def _on_external_drop(
        self, launcher_id: str, source_key: str, target_key: str, index: int
    ) -> None:
        visible = self._dest_visible(target_key)
        self.cfg.move_launcher(launcher_id, source_key, target_key, index, visible)
        fill_main_dropdown(self.dropdown, self.cfg)
        if self.container_menu.open_id:
            self._show_container_menu(self.container_menu.open_id, force=True)
        if self.execute_menu.open_id:
            self._show_execute_members(self.execute_menu.open_id, force=True)

    def _on_drag_finished(self) -> None:
        self.container_menu.hide_if_left()
        self.execute_menu.hide_if_left()
        # The mouse grab swallows leave events. Keep whichever list is under
        # the pointer, and hide the session when the pointer is over none of them.
        if self._pointer_over_any():
            self._cancel_hide()
            return
        if self._should_hide_on_leave():
            self._schedule_hide()

    def _on_container_reordered(self, ordered_ids: list[str]) -> None:
        if self.container_menu.open_id:
            self.cfg.reorder_container_members(self.container_menu.open_id, ordered_ids)

    def _on_execute_members_reordered(self, ordered_ids: list[str]) -> None:
        if self.execute_menu.open_id:
            self.cfg.reorder_group_members(self.execute_menu.open_id, ordered_ids)

    # ------------------------------------------------------------ launching

    def _notify(self, title: str, text: str) -> None:
        if self.tray.isVisible():
            self.tray.showMessage(title, text, QSystemTrayIcon.MessageIcon.Information, 1200)

    def _on_launch(self, launcher: Launcher) -> None:
        try:
            launch(launcher)
            self._notify("Launched", launcher.name)
        except Exception as exc:  # any failure is shown to the user
            stay_on_top_warning(
                self.trigger,
                "Launch failed",
                f"Could not launch '{launcher.name}':\n{exc}",
            )
        finally:
            if not self.settings.pinned_open:
                self._collapse_open_lists()
            else:
                self.container_menu.hide()
                self.execute_menu.hide()
                # Keep the pinned list fully open after the click.
                QTimer.singleShot(50, self.dropdown.ensure_visible_and_sized)
                QTimer.singleShot(55, lambda: self._keep_arrow_on_top(self.dropdown))

    def _on_group_launch(self, row: Launcher) -> None:
        group = self._group_by_id(row.id)
        if group is None:
            return
        steps = execution_steps(group, self.cfg.config.launchers)
        if self.settings.pinned_open:
            self.group_panel.force_hide()
            self.container_menu.hide()
            self.execute_menu.hide()
        else:
            self._collapse_open_lists()
        if not steps:
            stay_on_top_warning(
                self.trigger,
                "Nothing to launch",
                f"'{group.name}' has no launchers.",
            )
            return
        errors: list[str] = []

        def on_error(item: Launcher, exc: Exception) -> None:
            errors.append(f"{item.name}: {exc}")

        def on_finished() -> None:
            if errors:
                stay_on_top_warning(self.trigger, "Launch failed", "\n".join(errors))

        self._notify("Started", group.name)
        run_group_steps(
            steps,
            launch,
            lambda delay, callback: QTimer.singleShot(delay, self.trigger, callback),
            gap_ms=GROUP_STEP_GAP_MS,
            on_error=on_error,
            on_finished=on_finished,
        )

    def _on_tray_clicked(self) -> None:
        self.container_menu.hide()
        self.execute_menu.hide()
        if self._groups_only():
            self.group_panel.force_hide()
        self.dropdown.position_adjacent(self.trigger)
        fill_main_dropdown(self.dropdown, self.cfg)
        if self.settings.pinned_open:
            self.dropdown.ensure_visible_and_sized()
        else:
            self.dropdown.start_show_animation()
        self._keep_arrow_on_top(self.dropdown)

    # -------------------------------------------------------------- dialogs

    def _confirm_delete(self, title: str, name: str) -> bool:
        reply = stay_on_top_question(
            self.trigger,
            title,
            f"Delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def show_add_dialog(self, existing: Launcher | None = None) -> None:
        dialog = AddEditDialog(existing, self.trigger, cfg=self.cfg)
        if not dialog.exec():
            return
        result = dialog.result_launcher
        if not result:
            return
        if existing:
            self.cfg.update_launcher(result)
        else:
            self.cfg.add_launcher(result)
        fill_main_dropdown(self.dropdown, self.cfg)
        self._refresh_open_container()
        self._sync_groups_after_change()

    def _on_edit_launcher(self, launcher: Launcher) -> None:
        self.show_add_dialog(launcher)
        if self.settings.pinned_open:
            self._apply_pinned_state()

    def _on_delete_launcher(self, launcher: Launcher) -> None:
        if not self._confirm_delete("Delete Launcher", launcher.name):
            return
        self.cfg.remove_launcher(launcher.id)
        self._refresh_open_list()

    def show_manager_dialog(self) -> None:
        ManagerDialog(self.cfg, self.trigger).exec()
        # Launchers may have changed. Rebuild, then restore the pin state.
        fill_main_dropdown(self.dropdown, self.cfg)
        self._refresh_open_container()
        self._sync_groups_after_change()
        self._apply_pinned_state()

    def show_group_dialog(self, existing: Group | None = None) -> None:
        dialog = GroupDialog(self.cfg, existing, self.trigger)
        dialog.launchers_changed.connect(self._refresh_open_list)
        accepted = bool(dialog.exec())
        result = dialog.result_group
        if accepted and result is not None:
            if existing is None:
                self.cfg.add_group(result)
            else:
                self.cfg.update_group(result)
        self._refresh_open_list()
        self._sync_groups_after_change()

    def show_group_manager(self) -> None:
        GroupManagerDialog(self.cfg, self.trigger).exec()
        self._refresh_open_list()
        self._sync_groups_after_change()

    def _on_group_edit(self, row: Launcher) -> None:
        group = self._group_by_id(row.id)
        if group is not None:
            self.show_group_dialog(group)

    def _on_group_delete(self, row: Launcher) -> None:
        group = self._group_by_id(row.id)
        if group is None or not self._confirm_delete("Delete Execute Group", group.name):
            return
        self.cfg.remove_group(group.id)
        self._sync_groups_after_change()

    def show_container_dialog(self, existing: ContainerGroup | None = None) -> None:
        dialog = ContainerDialog(self.cfg, existing, self.trigger)
        dialog.launchers_changed.connect(self._refresh_open_list)
        accepted = bool(dialog.exec())
        result = dialog.result_group
        if accepted and result is not None:
            if existing is None:
                self.cfg.add_container_group(result)
            else:
                self.cfg.update_container_group(result)
        self._refresh_open_list()

    def show_container_manager(self) -> None:
        ContainerManagerDialog(self.cfg, self.trigger).exec()
        self._refresh_open_list()

    def _on_container_edit(self, group_id: str) -> None:
        group = self._container_by_id(group_id)
        if group is not None:
            self.show_container_dialog(group)

    def _on_container_delete(self, group_id: str) -> None:
        group = self._container_by_id(group_id)
        if group is None or not self._confirm_delete("Delete Container Group", group.name):
            return
        self.cfg.remove_container_group(group.id)
        self.container_menu.hide()
        self._refresh_open_list()

    # ------------------------------------------------------ menu switches

    def _on_pin_toggled(self, checked: bool) -> None:
        self.cfg.update_settings(pinned_open=checked)
        self._apply_pinned_state()

    def _on_filter_toggled(self, checked: bool) -> None:
        self.cfg.update_settings(show_filter_box=checked)
        for panel in (self.dropdown, self.group_panel, self.container_panel, self.execute_panel):
            panel.refresh_filter_visibility()
        if self._groups_only() and self.group_panel.isVisible():
            self.group_panel.update_height_for_content()
            self.group_panel.position_adjacent(self.trigger)
        elif self._groups_beside_enabled() and self.group_panel.isVisible():
            self.group_panel.update_height_for_content()
            self._place_groups_beside()
            if self.dropdown.isVisible():
                self.dropdown.update_height_for_content()
        elif self.dropdown.isVisible():
            self.dropdown.update_height_for_content()
            if self.settings.pinned_open:
                self.dropdown.position_adjacent(self.trigger)

    def _on_greeting_toggled(self, checked: bool) -> None:
        self.cfg.update_settings(show_startup_greeting=checked)
        if checked:
            self.greeting.show_again(self.trigger)
        else:
            self.greeting.dismiss_for_session()
        self._follow_trigger()

    def _on_show_groups_toggled(self, checked: bool) -> None:
        self.cfg.update_settings(show_groups=checked)
        if self._groups_only():
            return
        if checked and (self.dropdown.isVisible() or self.settings.pinned_open):
            self._show_groups_beside()
        elif not checked:
            self._hide_groups_beside()

    def _apply_opacity(self, percent: int | None = None) -> None:
        if percent is None:
            percent = self.settings.opacity_percent
        value = clamp_opacity_percent(percent) / 100
        self.trigger.setWindowOpacity(value)
        for panel in (self.dropdown, self.group_panel, self.container_panel, self.execute_panel):
            if panel.isVisible() and not panel.is_closing():
                panel.setWindowOpacity(value)

    def _on_opacity_changed(self, percent: int) -> None:
        self._update_settings_soon(opacity_percent=percent)
        self._apply_opacity(percent)

    def _update_settings_soon(self, **changes) -> None:
        """Apply now, write the config file once the changes stop."""
        self.cfg.update_settings(save=False, **changes)
        self.save_timer.start()

    def flush_pending_save(self) -> None:
        if self.save_timer.isActive():
            self.save_timer.stop()
            self.cfg.save()

    def _apply_color_scheme(self) -> None:
        self.trigger.update()
        for panel in (self.dropdown, self.group_panel, self.container_panel, self.execute_panel):
            panel.apply_theme()
        self.greeting.apply_theme()
        self.tray.setIcon(tray_icon())

    def _on_color_scheme(self, scheme_id: str) -> None:
        use(scheme_id)
        self.cfg.update_settings(color_scheme=scheme_id)
        self._apply_color_scheme()

    # ------------------------------------------------------------ geometry

    def _move_trigger_to_default(self) -> None:
        x, y = DEFAULT_POSITION
        self.trigger.resize(DEFAULT_TRIGGER_WIDTH, DEFAULT_TRIGGER_HEIGHT)
        self.trigger.move(x, y)
        self.cfg.update_settings(
            trigger_width=DEFAULT_TRIGGER_WIDTH,
            trigger_height=DEFAULT_TRIGGER_HEIGHT,
            position_x=x,
            position_y=y,
        )

    def _reset_if_off_screen(self) -> None:
        """A saved position can be off screen after a monitor change."""
        for screen in QApplication.screens():
            if screen.availableGeometry().intersects(QRect(self.trigger.pos(), self.trigger.size())):
                return
        self._move_trigger_to_default()

    def reset_position_and_size(self) -> None:
        self._move_trigger_to_default()
        self.trigger.raise_()
        self._follow_trigger()

    def _save_position(self, x: int, y: int) -> None:
        self.cfg.update_settings(position_x=x, position_y=y)
        self._follow_trigger()

    def _save_size(self, width: int, height: int) -> None:
        self.cfg.update_settings(
            trigger_width=width,
            trigger_height=height,
            position_x=self.trigger.x(),
            position_y=self.trigger.y(),
        )
        # The hint asked them to resize. Hide it for this launch.
        self.greeting.dismiss_for_session()
        self._follow_trigger()

    def _save_trigger_geometry(self) -> None:
        """Keep the arrow's size and position across a restart, without the greeting rim."""
        width, height = self.trigger.width(), self.trigger.height()
        if width < 20 or height < 20:
            return
        self.cfg.update_settings(
            trigger_width=width,
            trigger_height=height,
            position_x=self.trigger.x(),
            position_y=self.trigger.y(),
        )

    def bring_forward(self) -> None:
        """Another copy of Runner was started. Show this one instead."""
        self.trigger.show()
        self.trigger.raise_()
        self.trigger.activateWindow()

    # -------------------------------------------------------------- reload

    def reload_config(self) -> None:
        """Re-read config.json after an outside edit and redraw everything from it."""
        self.flush_pending_save()
        self.cfg.reload()
        use(self.settings.color_scheme)
        self.hide_timer.setInterval(self.settings.hover_delay_ms)
        fill_main_dropdown(self.dropdown, self.cfg)
        self.trigger.update_size_from_settings()
        self.trigger.move(self.settings.position_x, self.settings.position_y)
        self._apply_color_scheme()
        self._apply_opacity()
        for panel in (self.dropdown, self.group_panel, self.container_panel, self.execute_panel):
            panel.refresh_filter_visibility()
        self._report_load_problems()
        if self._groups_only():
            self._sync_groups_after_change()
            return
        if self.settings.pinned_open:
            self.dropdown.position_adjacent(self.trigger)
            self.dropdown.ensure_visible_and_sized()
            if self._groups_beside_enabled():
                self._show_groups_beside()

    def _report_load_problems(self) -> None:
        problems = self.cfg.load_problems
        if not problems:
            return
        shown = problems[:_MAX_PROBLEMS_SHOWN]
        extra = len(problems) - len(shown)
        text = "Runner found problems in its config file:\n\n" + "\n".join(
            f"• {line}" for line in shown
        )
        if extra > 0:
            text += f"\n• …and {extra} more."
        # Report once per load.
        self.cfg.load_problems = []
        stay_on_top_warning(self.trigger, "Config problems", text)
