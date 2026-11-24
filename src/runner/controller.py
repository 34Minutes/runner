"""Wires the arrow, the lists, the dialogs, and the tray together.

There are six lists:

- the main popup (launchers and container rows),
- the execute-groups list,
- the container-groups list,
- the schedules list (execute groups that run on dates),
- a container's launchers, beside its row in the main popup or the
  container-groups list,
- an execute group's launchers, beside its row in the execute-groups list.

PopupMode says which lists the arrow opens. In MAIN the execute-groups list
sits beside the main popup when Show execute groups is on. GROUPS_ONLY,
CONTAINERS_ONLY, and SCHEDULES_ONLY were opened from the arrow menu: that one
list is shown on its own and the main popup is hidden.

A scheduled execute group shows only in the schedules list. The Scheduler
runs it on its dates.

The two side lists are SideMenus. Each one is open for at most one row,
and it fades out a moment after the pointer leaves both it and that row.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import datetime
from enum import Enum, auto

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
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
from .moves import container_token, member_launchers, merge_visible_order, visible_main_tokens
from .api import RunnerApi, is_write
from .schedule import execute_groups, format_when, group_next_run, scheduled_groups
from .scheduler import Scheduler
from .ui.add_dialog import AddEditDialog
from .ui.container_dialog import ContainerDialog
from .ui.container_manager import ContainerManagerDialog
from .ui.dropdown import DropdownPanel, LockedPairMotion, SubmenuButton
from .ui.greeting import StartupGreeting, clamp_trigger_to_screen, ensure_visible_trigger_size
from .ui.group_dialog import GroupDialog
from .ui.group_manager import GroupManagerDialog, ScheduleManagerDialog
from .ui.help_dialog import HelpWindow
from .ui.launch_button import LaunchButton
from .ui.manager_dialog import ManagerDialog
from .ui.stay_on_top import on_dialog_open
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
# The schedules list grows to fit a name and its next run, up to this width.
SCHEDULE_LIST_MAX_W = 460
# A row's text inset, the list's frame, and room for its scrollbar.
SCHEDULE_ROW_PADDING = 64
# Shown at most this many config problems in the warning. The rest are counted.
_MAX_PROBLEMS_SHOWN = 12


class PopupMode(Enum):
    MAIN = auto()  # The main popup, with execute groups beside it when that switch is on.
    GROUPS_ONLY = auto()  # The execute-groups list on its own, from the arrow menu.
    CONTAINERS_ONLY = auto()  # The container-groups list on its own, from the arrow menu.
    SCHEDULES_ONLY = auto()  # The schedules list on its own, from the arrow menu.


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


def fill_main_dropdown(dropdown: DropdownPanel, cfg: ConfigManager) -> None:
    """Launcher rows and container rows, in the saved mixed order."""
    dropdown.set_submenu_items(
        [(group.id, group.name) for group in cfg.config.container_groups]
    )
    dropdown.rebuild_buttons(cfg.get_main_view_launchers())
    dropdown.apply_token_order(visible_main_tokens(cfg.config))


class _ArrowAboveActiveList(QObject):
    """Put the arrow back on top when a list becomes the active window.

    On macOS the window that becomes key is ordered to the front after any
    raise that came before it, so a list that takes focus as it opens would
    otherwise end up over the arrow and the greeting.
    """

    def __init__(self, restack: Callable[[], None]) -> None:
        super().__init__()
        self._restack = restack

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if event.type() == QEvent.Type.WindowActivate:
            QTimer.singleShot(0, self._restack)
        return False


class RunnerController:
    """Owns the widgets and keeps them in step with the config."""

    def __init__(self, app: QApplication, cfg: ConfigManager) -> None:
        self.app = app
        self.cfg = cfg
        self.mode = PopupMode.MAIN
        # True while the arrow itself is being dragged. The lists stay closed.
        self._arrow_dragging = False

        self._build_widgets()
        self.help_window: HelpWindow | None = None
        # Started once the arrow is up. Runs missed while Runner was closed are skipped.
        self.scheduler = Scheduler(lambda: self.cfg.config.groups, self._run_scheduled)
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
        self.container_list = DropdownPanel(cfg.config, honor_pin=False)
        self.schedule_list = DropdownPanel(cfg.config, honor_pin=False, allow_reorder=False)

        self.dropdown.set_mix_rows(True)
        self.dropdown.set_drag_source_key("main")

        self.group_panel.set_list_copy(placeholder="Filter execute groups...", empty_hint="")
        self.group_panel.set_order_ids(lambda: [group.id for group in self._execute_groups()])
        self.group_panel.set_row_tooltip(self._group_row_tooltip)
        self.group_panel.set_heading("Execute Groups")
        self.group_panel.set_drag_source_key("groups")
        self.group_panel.set_emit_row_hover(True)

        # Container rows on their own, drawn as they are in the main popup.
        self.container_list.set_list_copy(placeholder="Filter container groups...", empty_hint="")
        self.container_list.set_heading("Container Groups")
        # Its rows are all container rows, which only drag in a mixed list.
        # It has no peers, so a row can only change place, never go into another.
        self.container_list.set_mix_rows(True)

        # Scheduled execute groups, each with its next run. A click edits it.
        self.schedule_list.set_list_copy(placeholder="Filter schedules...", empty_hint="")
        self.schedule_list.set_heading("Schedules")
        self.schedule_list.set_row_tooltip(self._schedule_row_tooltip)
        self.schedule_list.set_emit_row_hover(True)
        # The list opened on its own from the arrow menu for each mode.
        self._standalone = {
            PopupMode.CONTAINERS_ONLY: self.container_list,
            PopupMode.SCHEDULES_ONLY: self.schedule_list,
        }

        self.container_panel.set_list_copy(
            placeholder="Filter launchers...", empty_hint="Nothing in this container."
        )
        self.execute_panel.set_list_copy(
            placeholder="Filter launchers...", empty_hint="Nothing in this execute group."
        )

        self.container_menu = SideMenu(
            self.container_panel, lambda group_id: self._container_host().submenu_button(group_id)
        )
        self.execute_menu = SideMenu(
            self.execute_panel, lambda group_id: self._execute_host().launcher_button(group_id)
        )
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
        self.greeting.set_avoid(lambda: [panel.frameGeometry() for panel in self._open_lists()])
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
        for panel in self._standalone.values():
            panel.hover_enter.connect(lambda p=panel: self._on_standalone_enter(p))
            panel.hover_leave.connect(lambda p=panel: self._on_standalone_leave(p))
            panel.closed.connect(lambda p=panel: self._on_standalone_closed(p))
        self.container_list.submenu_hovered.connect(self._show_container_menu)
        self.container_list.submenu_left.connect(self.container_menu.on_row_left)
        self.schedule_list.row_hovered.connect(self._show_execute_members)
        self.schedule_list.row_left.connect(self.execute_menu.on_row_left)
        self.group_panel.row_hovered.connect(self._show_execute_members)
        self.group_panel.row_left.connect(self.execute_menu.on_row_left)
        on_dialog_open(self._make_room_for_dialog)
        self._restack_on_activate = _ArrowAboveActiveList(self._restack_after_activation)
        for panel in self._all_lists():
            panel.installEventFilter(self._restack_on_activate)

    def _make_room_for_dialog(self) -> None:
        """A dialog is opening: close the lists that are only open on hover.

        The pointer is about to leave them for the dialog anyway, and the
        dialog would open over them. A pinned launcher list stays, and the
        dialog opens clear of it.
        """
        if self._arrow_dragging or not self.trigger.isVisible():
            return
        self.hide_timer.stop()
        self.container_menu.hide()
        self.execute_menu.hide()
        if self._one_list_only():
            for panel in (self.group_panel, *self._standalone.values()):
                if panel.isVisible():
                    panel.force_hide()  # its close handler restores a pinned list
            return
        if self.settings.pinned_open:
            return
        for panel in (self.dropdown, self.group_panel):
            if panel.isVisible():
                panel.force_hide()

    def _restack_after_activation(self) -> None:
        if self.trigger.isVisible() and not self._arrow_dragging:
            self._keep_arrow_on_top()

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
        self.container_list.submenu_edit_requested.connect(self._on_container_edit)
        self.container_list.submenu_delete_requested.connect(self._on_container_delete)
        self.container_list.rows_reordered.connect(self._on_container_list_reordered)
        container.reordered.connect(self._on_container_reordered)
        execute.reordered.connect(self._on_execute_members_reordered)

        groups.launch_requested.connect(self._on_group_launch)
        groups.edit_requested.connect(self._on_group_edit)
        groups.delete_requested.connect(self._on_group_delete)
        groups.reordered.connect(self.cfg.reorder_groups)

        schedules = self.schedule_list
        schedules.launch_requested.connect(self._on_schedule_click)  # edits it, or runs it
        schedules.edit_requested.connect(self._on_group_edit)
        schedules.delete_requested.connect(self._on_group_delete)

    def _connect_trigger_menu(self) -> None:
        trigger = self.trigger
        trigger.request_add.connect(lambda: self.show_add_dialog())
        trigger.request_manage.connect(self.show_manager_dialog)
        trigger.request_reset.connect(self.reset_position_and_size)
        trigger.request_help.connect(self.show_help)
        trigger.request_exit.connect(self.app.quit)
        trigger.request_add_group.connect(lambda: self.show_group_dialog())
        trigger.request_manage_groups.connect(self.show_group_manager)
        trigger.request_groups.connect(self._show_group_panel)
        trigger.request_containers.connect(self._show_container_list)
        trigger.request_schedules.connect(self._show_schedule_list)
        trigger.request_add_schedule.connect(lambda: self.show_group_dialog(scheduled=True))
        trigger.request_manage_schedules.connect(self.show_schedule_manager)
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
        self.trigger.drag_started.connect(self._on_arrow_drag_started)
        self.trigger.drag_finished.connect(self._on_arrow_drag_finished)
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
        self.scheduler.start()

    # ------------------------------------------------------------ lookups

    def _execute_groups(self) -> list[Group]:
        """Execute groups run by hand. Scheduled ones are only in the schedules list."""
        return execute_groups(self.cfg.config.groups)

    def _scheduled_groups(self) -> list[Group]:
        return scheduled_groups(self.cfg.config.groups)

    def _schedule_row_tooltip(self, row: Launcher) -> str:
        group = self._group_by_id(row.id)
        lines = [f"Schedule: {group.name}" if group else "Schedule"]
        if group is not None:
            lines.append(f"Runs {len(group.members)} launcher{'' if len(group.members) == 1 else 's'}")
            if group.show_contents:
                lines.append("Hover to see its launchers")
        lines.append("Click to run it now" if group is not None and group.click_runs else "Click to edit its dates")
        lines.append("Right-click to edit or delete")
        return "\n".join(lines)

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

    def _containers_only(self) -> bool:
        return self.mode is PopupMode.CONTAINERS_ONLY

    def _schedules_only(self) -> bool:
        return self.mode is PopupMode.SCHEDULES_ONLY

    def _one_list_only(self) -> bool:
        """A list opened on its own from the arrow menu is showing instead of the main popup."""
        return self.mode is not PopupMode.MAIN

    def _standalone_panel(self) -> DropdownPanel | None:
        """The container or schedules list, when the arrow menu opened it on its own."""
        return self._standalone.get(self.mode)

    def _all_lists(self) -> tuple[DropdownPanel, ...]:
        return (
            self.dropdown,
            self.group_panel,
            self.container_list,
            self.schedule_list,
            self.container_panel,
            self.execute_panel,
        )

    def _container_host(self) -> DropdownPanel:
        """The list whose container rows open the container's launchers."""
        return self.container_list if self._containers_only() else self.dropdown

    def _execute_host(self) -> DropdownPanel:
        """The list whose group rows open that group's launchers."""
        return self.schedule_list if self._schedules_only() else self.group_panel

    def _pointer_over_any(self, *, trigger: bool = True) -> bool:
        panels = list(self._all_lists())
        if trigger:
            panels.append(self.trigger)
        return any(_pointer_over(widget) for widget in panels)

    def _any_drag(self) -> bool:
        return any(
            panel.is_dragging()
            for panel in self._all_lists()
        )

    def _keep_arrow_on_top(self, *panels: DropdownPanel) -> None:
        """The arrow stays above the lists that open from it.

        A greeting that is showing sits between them: its rim hugs the arrow,
        and its bubble keeps clear of the lists. On macOS only the raise
        orders these windows; stackUnder() is for the other platforms.
        """
        self.trigger.raise_()
        for panel in panels:
            panel.stackUnder(self.trigger)
        self.greeting.stack_with(self.trigger, self._open_lists())

    def _open_lists(self) -> list[DropdownPanel]:
        return [panel for panel in self._all_lists() if panel.isVisible()]

    # -------------------------------------------------------------- hiding

    def _schedule_hide(self) -> None:
        self.hide_timer.start()

    def _cancel_hide(self) -> None:
        self.hide_timer.stop()
        for panel in self._all_lists():
            panel.cancel_hide()

    def _should_hide_on_leave(self) -> bool:
        return self._one_list_only() or not self.settings.pinned_open

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
        if self.container_list.isVisible():
            self.container_list.force_hide()

    def _do_hide(self) -> None:
        if self._pointer_over_any():
            return
        _decay(self.container_panel)
        _decay(self.execute_panel)
        if self._groups_only():
            self.group_panel.start_hide_animation()
            return
        standalone = self._standalone_panel()
        if standalone is not None:
            standalone.start_hide_animation()
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
            for group in self._execute_groups()
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
        if not self._execute_groups():
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
        self._hide_standalone()
        if not self._execute_groups():
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
        # A list closed by an arrow drag opens again where the arrow lands.
        if self.group_panel.isVisible() or self._standalone_panel() is not None or self._arrow_dragging:
            return
        self.mode = PopupMode.MAIN
        if self.settings.pinned_open:
            self._apply_pinned_state()

    # ------------------------------- container groups and schedules, alone

    def _standalone_items(self, mode: PopupMode) -> bool:
        """Whether that list has anything to show."""
        if mode is PopupMode.CONTAINERS_ONLY:
            return bool(self.cfg.config.container_groups)
        return bool(self._scheduled_groups())

    def _refresh_standalone(self, mode: PopupMode) -> None:
        panel = self._standalone[mode]
        if mode is PopupMode.CONTAINERS_ONLY:
            panel.set_submenu_items([(group.id, group.name) for group in self.cfg.config.container_groups])
            panel.rebuild_buttons([])
        else:
            now = datetime.now()
            rows = []
            for group in self._scheduled_groups():
                upcoming = group_next_run(group, now)
                when = (
                    f"next {format_when(upcoming, with_year=upcoming.year != now.year)}"
                    if upcoming else "no upcoming runs"
                )
                rows.append(Launcher(id=group.id, name=f"{group.name}  ·  {when}", command=""))
            panel.rebuild_buttons(rows)
            self._fit_schedule_width(panel)
        if panel.isVisible():
            panel.update_height_for_content()

    def _fit_schedule_width(self, panel: DropdownPanel) -> None:
        """Wide enough for a name and its next run, between the list width and SCHEDULE_LIST_MAX_W."""
        base = self.settings.dropdown_width
        buttons = panel._launch_buttons()
        if buttons:
            metrics = buttons[0].fontMetrics()
            need = max(metrics.horizontalAdvance(b.launcher.name) for b in buttons) + SCHEDULE_ROW_PADDING
        else:
            need = base
        panel.setFixedWidth(max(base, min(need, SCHEDULE_LIST_MAX_W)))

    def _refresh_container_list(self) -> None:
        self._refresh_standalone(PopupMode.CONTAINERS_ONLY)

    def _show_container_list(self) -> None:
        """The container-groups list on its own, from the arrow menu.

        It opens beside the arrow as the execute-groups list does. Hovering a
        row opens that container's launchers beside it.
        """
        self._show_standalone(PopupMode.CONTAINERS_ONLY)

    def _show_schedule_list(self) -> None:
        """The schedules list on its own, from the arrow menu.

        Each row is a scheduled group and its next run. A click opens it to
        edit its dates; hovering opens its launchers when Show group contents is on.
        """
        self._show_standalone(PopupMode.SCHEDULES_ONLY)

    def _show_standalone(self, mode: PopupMode) -> None:
        self.container_menu.hide()
        self.execute_menu.hide()
        if not self._standalone_items(mode):
            self._hide_standalone()
            return
        panel = self._standalone[mode]
        self.mode = mode
        self._cancel_hide()
        for other in (self.dropdown, self.group_panel, *self._standalone.values()):
            if other is panel:
                continue
            other.use_position_hook(None)
            if other.isVisible():
                other.force_hide()
        self._refresh_standalone(mode)
        panel.position_adjacent(self.trigger)
        if panel.isVisible() and not panel.is_closing():
            panel.ensure_visible_and_sized()
        else:
            panel.start_show_animation()
        self._keep_arrow_on_top(panel)

    def _hide_standalone(self) -> None:
        """Back to the main popup's mode. The pinned list returns when pinned."""
        panel = self._standalone_panel()
        self.mode = PopupMode.MAIN
        if panel is not None and panel.isVisible():
            panel.force_hide()
        elif panel is not None and self.settings.pinned_open:
            self._apply_pinned_state()

    def _hide_container_list(self) -> None:
        self._hide_standalone()

    def _on_standalone_closed(self, panel: DropdownPanel) -> None:
        # A hide that was already running can finish after the list is shown again.
        if panel.isVisible() or self._standalone_panel() is not panel or self._arrow_dragging:
            return
        self.container_menu.hide()
        self.execute_menu.hide()
        self.mode = PopupMode.MAIN
        if self.settings.pinned_open:
            self._apply_pinned_state()

    def _side_for(self, panel: DropdownPanel) -> SideMenu:
        return self.container_menu if panel is self.container_list else self.execute_menu

    def _on_standalone_enter(self, panel: DropdownPanel) -> None:
        self._cancel_hide()
        self._side_for(panel).timer.stop()
        if panel.is_closing() and self._standalone_panel() is panel:
            panel.cancel_close()

    def _on_standalone_leave(self, panel: DropdownPanel) -> None:
        if not panel.isVisible():
            return  # a late leave from a list that is already closed
        side = self._side_for(panel)
        if _pointer_over(side.panel):
            return
        side.schedule_hide()
        if self._standalone_panel() is panel:
            self._schedule_hide()

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
        for panel in self._standalone.values():
            if panel.isVisible():
                panel.force_hide()
        fill_main_dropdown(self.dropdown, self.cfg)
        self.dropdown.position_adjacent(self.trigger)
        groups_too = self._groups_beside_enabled() and bool(self._execute_groups())
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
        if self._one_list_only():
            return
        if self._arrow_dragging:
            return  # the drop reopens a pinned list where the arrow lands
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
        if self._arrow_dragging:
            return
        if self._groups_only() and self.group_panel.isVisible():
            self.group_panel.use_position_hook(None)
            self.group_panel.position_adjacent(self.trigger)
            self.group_panel.ensure_visible_and_sized()
            self._keep_arrow_on_top(self.group_panel)
            return
        standalone = self._standalone_panel()
        if standalone is not None:
            if standalone.isVisible():
                standalone.position_adjacent(self.trigger)
                standalone.ensure_visible_and_sized()
                self._keep_arrow_on_top(standalone)
            return
        if self.locked_pair.is_presented():
            if self._groups_beside_enabled() and self._execute_groups():
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

    def _on_arrow_drag_started(self) -> None:
        """Moving the arrow closes every list at once, pinned or not."""
        self._arrow_dragging = True
        self.hide_timer.stop()
        self.container_menu.hide()
        self.execute_menu.hide()
        for panel in self._all_lists():
            if panel.isVisible():
                panel.force_hide()

    def _on_arrow_drag_finished(self) -> None:
        """The lists open again where the arrow was dropped, as a hover opens them."""
        self._arrow_dragging = False
        if self.settings.pinned_open:
            self._apply_pinned_state()
        self._on_trigger_enter()
        # A release noticed late can come with the pointer elsewhere. Then no
        # leave will arrive to close the lists, so start the usual fade now.
        if not self._pointer_over_any() and self._should_hide_on_leave():
            self._schedule_hide()

    def _on_trigger_enter(self) -> None:
        if self._arrow_dragging:
            return
        self._cancel_hide()
        self.container_menu.hide()
        self.execute_menu.hide()
        if self._groups_only():
            self.group_panel.position_adjacent(self.trigger)
            if self.group_panel.is_closing() or not self.group_panel.isVisible():
                self._show_group_panel()
            self._keep_arrow_on_top(self.group_panel)
            return
        standalone = self._standalone_panel()
        if standalone is not None:
            standalone.position_adjacent(self.trigger)
            if standalone.is_closing() or not standalone.isVisible():
                self._show_standalone(self.mode)
            self._keep_arrow_on_top(standalone)
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
        # A list that was just closed can still report the pointer leaving.
        # That must not start a hide for the list opened in its place.
        if not self.dropdown.isVisible():
            return
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
        if not self.group_panel.isVisible():
            return  # a late leave from a list that is already closed
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
            or _pointer_over(self.container_list)
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
            or _pointer_over(self.schedule_list)
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
        if self._containers_only():
            return True
        return not (self.group_panel.isVisible() and self.group_panel.x() >= self.dropdown.x())

    def _execute_prefer_right(self) -> bool:
        """Open away from the main list when both lists are on screen."""
        if self._schedules_only():
            return True
        return not (self.dropdown.isVisible() and self.dropdown.x() >= self.group_panel.x())

    def _place_container(self) -> None:
        button = self.container_menu.anchor()
        if button is not None:
            self.container_panel.position_next_to(
                self._container_host(), button, prefer_right=self._container_prefer_right()
            )

    def _place_execute_members(self) -> None:
        button = self.execute_menu.anchor()
        if button is not None:
            self.execute_panel.position_next_to(
                self._execute_host(), button, prefer_right=self._execute_prefer_right()
            )

    def _on_container_list_reordered(self, tokens: list[str]) -> None:
        """Container Groups was reordered by drag. Save it as the container order."""
        prefix = container_token("")
        moved = [token[len(prefix):] for token in tokens if token.startswith(prefix)]
        # A filter can hide rows. Those keep their places; only the shown ones move.
        shown = set(moved)
        current = [group.id for group in self.cfg.config.container_groups]
        self.cfg.reorder_container_groups(merge_visible_order([(gid, gid in shown) for gid in current], moved))

    def _show_container_menu(self, group_id: str, *, force: bool = False) -> None:
        menu, panel = self.container_menu, self.container_panel
        # This panel is the source while a launcher is dragged out of it.
        if panel.is_dragging():
            return
        # A container row being dragged only changes place. Opening another
        # container's submenu under it would offer a drop it cannot make.
        if any(lst.dragging_submenu() for lst in (self.dropdown, self.container_list)):
            menu.hide()
            return
        host = self._container_host()
        group = self._container_by_id(group_id)
        button = host.submenu_button(group_id) if group is not None else None
        if not host.isVisible() or button is None or not button.isVisible():
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
        self._keep_arrow_on_top(host, panel)

    def _show_execute_members(self, group_id: str, *, force: bool = False) -> None:
        menu, panel = self.execute_menu, self.execute_panel
        host = self._execute_host()
        if panel.is_dragging() or host.is_dragging():
            return
        group = self._group_by_id(group_id)
        if group is None or not host.isVisible():
            menu.hide()
            return
        # Show group contents defaults off. Hover and drag-over stay collapsed.
        if not group.show_contents:
            if menu.open_id is not None:
                menu.hide()
            return
        button = host.launcher_button(group_id)
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
        self._keep_arrow_on_top(host, panel)

    def _refresh_open_container(self) -> None:
        if self.container_menu.open_id and self.container_panel.isVisible():
            self._show_container_menu(self.container_menu.open_id, force=True)

    def _refresh_open_execute(self) -> None:
        if self.execute_menu.open_id and self.execute_panel.isVisible():
            self._show_execute_members(self.execute_menu.open_id, force=True)

    def _refresh_open_list(self) -> None:
        fill_main_dropdown(self.dropdown, self.cfg)
        standalone = self._standalone_panel()
        if standalone is not None:
            if not self._standalone_items(self.mode):
                self._hide_standalone()
            else:
                self._refresh_standalone(self.mode)
                if standalone.isVisible():
                    standalone.position_adjacent(self.trigger)
                    standalone.ensure_visible_and_sized()
        self._refresh_open_container()
        self._refresh_open_execute()
        if self.settings.pinned_open:
            self._apply_pinned_state()

    def _sync_groups_after_change(self) -> None:
        """Keep an open groups list in step with add, edit, and delete.

        The member list closes when its execute group is gone. With no groups
        left, the list hides.
        """
        self.scheduler.refresh()
        if self.execute_menu.open_id and self._group_by_id(self.execute_menu.open_id) is None:
            self.execute_menu.hide()
        elif self.execute_menu.open_id:
            self._refresh_open_execute()
        if self._schedules_only():
            self._refresh_open_list()
            return
        if self._groups_only():
            if not self._execute_groups():
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
                if self._standalone_panel() is not None:
                    self._hide_standalone()
                # Keep the pinned list fully open after the click.
                QTimer.singleShot(50, self.dropdown.ensure_visible_and_sized)
                QTimer.singleShot(55, lambda: self._keep_arrow_on_top(self.dropdown))

    def _on_group_launch(self, row: Launcher) -> None:
        group = self._group_by_id(row.id)
        if group is None:
            return
        if self.settings.pinned_open:
            self.group_panel.force_hide()
            self.container_menu.hide()
            self.execute_menu.hide()
        else:
            self._collapse_open_lists()
        self._start_group(group, "Started")

    def _on_schedule_click(self, row: Launcher) -> None:
        """A click in the Schedules list: open the schedule, or run it if it is set to."""
        group = self._group_by_id(row.id)
        if group is None:
            return
        if not group.click_runs:
            self.show_group_dialog(group)
            return
        self._collapse_open_lists()
        if self.schedule_list.isVisible() and not self.settings.pinned_open:
            self.schedule_list.force_hide()
        self._start_group(group, "Started")

    def _run_scheduled(self, group: Group) -> None:
        """The scheduler's turn: run it without touching the lists the user has open."""
        self._start_group(group, "Scheduled run")
        if self._schedules_only():
            self._refresh_standalone(PopupMode.SCHEDULES_ONLY)

    def _start_group(self, group: Group, notice: str) -> None:
        steps = execution_steps(group, self.cfg.config.launchers)
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

        self._notify(notice, group.name)
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
        if self._standalone_panel() is not None:
            self._hide_standalone()
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

    def show_group_dialog(self, existing: Group | None = None, *, scheduled: bool = False) -> None:
        dialog = GroupDialog(self.cfg, existing, self.trigger, scheduled=scheduled)
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

    def show_schedule_manager(self) -> None:
        ScheduleManagerDialog(self.cfg, self.trigger).exec()
        self._refresh_open_list()
        self._sync_groups_after_change()

    def _on_group_edit(self, row: Launcher) -> None:
        group = self._group_by_id(row.id)
        if group is not None:
            self.show_group_dialog(group)

    def _on_group_delete(self, row: Launcher) -> None:
        group = self._group_by_id(row.id)
        title = "Delete Schedule" if group is not None and group.scheduled else "Delete Execute Group"
        if group is None or not self._confirm_delete(title, group.name):
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
        for panel in self._all_lists():
            panel.refresh_filter_visibility()
        if self._groups_only() and self.group_panel.isVisible():
            self.group_panel.update_height_for_content()
            self.group_panel.position_adjacent(self.trigger)
        elif self._standalone_panel() is not None and self._standalone_panel().isVisible():
            self._standalone_panel().update_height_for_content()
            self._standalone_panel().position_adjacent(self.trigger)
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
            self._keep_arrow_on_top()
        else:
            self.greeting.dismiss_for_session()
        self._follow_trigger()

    def _on_show_groups_toggled(self, checked: bool) -> None:
        self.cfg.update_settings(show_groups=checked)
        if self._one_list_only():
            return
        if checked and (self.dropdown.isVisible() or self.settings.pinned_open):
            self._show_groups_beside()
        elif not checked:
            self._hide_groups_beside()

    def _apply_opacity(self, percent: int | None = None) -> None:
        if percent is None:
            percent = self.settings.opacity_percent
        # Only the arrow. The lists stay solid so their rows are easy to read.
        self.trigger.setWindowOpacity(clamp_opacity_percent(percent) / 100)

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
        for panel in self._all_lists():
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
        # Save first: the arrow treats a size that differs from the saved one
        # as the user's own resize, which would dismiss the reset's greeting.
        self.cfg.update_settings(
            trigger_width=DEFAULT_TRIGGER_WIDTH,
            trigger_height=DEFAULT_TRIGGER_HEIGHT,
            position_x=x,
            position_y=y,
        )
        self.trigger.resize(DEFAULT_TRIGGER_WIDTH, DEFAULT_TRIGGER_HEIGHT)
        self.trigger.move(x, y)

    def _reset_if_off_screen(self) -> None:
        """A saved position can be off screen after a monitor change."""
        for screen in QApplication.screens():
            if screen.availableGeometry().intersects(QRect(self.trigger.pos(), self.trigger.size())):
                return
        self._move_trigger_to_default()

    def reset_position_and_size(self) -> None:
        # A resize or move whose release never arrived would pull the arrow
        # straight back out to the pointer.
        self.trigger.cancel_pointer_gesture()
        self._move_trigger_to_default()
        self.trigger.raise_()
        self._follow_trigger()
        # The arrow just jumped to the default spot: point it out, and remind
        # them they can resize and move it. Shown whatever the greeting switch says.
        self.greeting.show_again(self.trigger, show_bubble=True, even_under_pointer=True)
        self._keep_arrow_on_top()

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

    # -------------------------------------------------------------- help

    def show_help(self) -> None:
        """The Help window, from the arrow menu. One at a time; a second Help brings it forward."""
        if self.help_window is None:
            self.help_window = HelpWindow(self.trigger)
        self.help_window.show()
        self.help_window.raise_()
        self.help_window.activateWindow()

    # ------------------------------------------------- outside requests

    def answer_outside_request(self, request: object) -> dict:
        """A request from `runner ctl`, through the private socket. See runner.api."""
        if is_write(request) and QApplication.activeModalWidget() is not None:
            # A dialog holds its own copy of what it edits and would save over the change.
            return {
                "ok": False,
                "error": "Runner has a window open. Close it in Runner, then try again.",
            }
        self.flush_pending_save()
        outcome = RunnerApi(self.cfg).execute(request)
        if outcome.changed:
            self._after_outside_change()
        return outcome.reply

    def _after_outside_change(self) -> None:
        fill_main_dropdown(self.dropdown, self.cfg)
        self._refresh_open_list()
        if self.container_menu.open_id and self._container_by_id(self.container_menu.open_id) is None:
            self.container_menu.hide()
        self._sync_groups_after_change()

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
        for panel in self._all_lists():
            panel.refresh_filter_visibility()
        self._report_load_problems()
        if self._groups_only():
            self._sync_groups_after_change()
            return
        self.scheduler.refresh()
        if self._standalone_panel() is not None:
            self._refresh_open_list()
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
