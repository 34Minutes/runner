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

from PySide6.QtCore import QPoint, QRect, QTimer
from PySide6.QtWidgets import QApplication

from .api import RunnerApi, is_write
from .config import (
    DEFAULT_TRIGGER_HEIGHT,
    DEFAULT_TRIGGER_WIDTH,
    ConfigManager,
    ContainerGroup,
    Group,
    Launcher,
)
from .dialog_coordinator import DialogCoordinator
from .drag_coordinator import DragCoordinator
from .elevation import warn_if_elevated
from .launch_coordinator import LaunchCoordinator
from .popup_coordinator import (
    SCHEDULE_LIST_MAX_W,
    SCHEDULE_ROW_PADDING,
    PopupCoordinator,
    PopupMode,
    SideMenu,
    _ArrowAboveActiveList,
    fill_main_dropdown,
)
from .schedule import execute_groups, scheduled_groups
from .scheduler import Scheduler
from .tray import create_tray, tray_icon
from .ui.dropdown import DropdownPanel, LockedPairMotion
from .ui.greeting import StartupGreeting, clamp_trigger_to_screen, ensure_visible_trigger_size
from .ui.help_dialog import HelpWindow
from .ui.stay_on_top import on_dialog_open
from .ui.stay_on_top import warning as stay_on_top_warning
from .ui.theme import use
from .ui.trigger import TriggerWidget, clamp_decay_ms, clamp_opacity_percent

if sys.platform == "win32":
    from .utils import windows as win_utils  # type: ignore
else:
    win_utils = None  # type: ignore

DEFAULT_POSITION = (100, 100)
# A slider writes the config this long after it stops moving.
SLIDER_SAVE_DELAY_MS = 400

__all__ = [
    "DEFAULT_POSITION",
    "SCHEDULE_LIST_MAX_W",
    "SCHEDULE_ROW_PADDING",
    "SLIDER_SAVE_DELAY_MS",
    "PopupMode",
    "RunnerController",
    "SideMenu",
    "create_tray",
    "fill_main_dropdown",
    "tray_icon",
]


class RunnerController:
    """Owns the widgets and keeps them in step with the config."""

    def __init__(self, app: QApplication, cfg: ConfigManager) -> None:
        self.app = app
        self.cfg = cfg
        self.mode = PopupMode.MAIN
        # True while the arrow itself is being dragged. The lists stay closed.
        self._arrow_dragging = False

        self.popups = PopupCoordinator(self)
        self.dialogs = DialogCoordinator(self)
        self.launches = LaunchCoordinator(self)
        self.drag = DragCoordinator(self)
        self._build_widgets()
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

    # -------------------------------------------- popups, hover & side menus

    def _make_room_for_dialog(self) -> None:
        self.popups.make_room_for_dialog()

    def _restack_after_activation(self) -> None:
        self.popups.restack_after_activation()

    def _groups_beside_enabled(self) -> bool:
        return self.popups.groups_beside_enabled()

    def _groups_only(self) -> bool:
        return self.popups.groups_only()

    def _containers_only(self) -> bool:
        return self.popups.containers_only()

    def _schedules_only(self) -> bool:
        return self.popups.schedules_only()

    def _one_list_only(self) -> bool:
        return self.popups.one_list_only()

    def _standalone_panel(self) -> DropdownPanel | None:
        return self.popups.standalone_panel()

    def _all_lists(self) -> tuple[DropdownPanel, ...]:
        return self.popups.all_lists()

    def _container_host(self) -> DropdownPanel:
        return self.popups.container_host()

    def _execute_host(self) -> DropdownPanel:
        return self.popups.execute_host()

    def _pointer_over_any(self, *, trigger: bool = True) -> bool:
        return self.popups.pointer_over_any(trigger=trigger)

    def _any_drag(self) -> bool:
        return self.popups.any_drag()

    def _keep_arrow_on_top(self, *panels: DropdownPanel) -> None:
        self.popups.keep_arrow_on_top(*panels)

    def _open_lists(self) -> list[DropdownPanel]:
        return self.popups.open_lists()

    def _schedule_hide(self) -> None:
        self.popups.schedule_hide()

    def _cancel_hide(self) -> None:
        self.popups.cancel_hide()

    def _should_hide_on_leave(self) -> bool:
        return self.popups.should_hide_on_leave()

    def _collapse_open_lists(self) -> None:
        self.popups.collapse_open_lists()

    def _do_hide(self) -> None:
        self.popups.do_hide()

    def _refresh_group_list(self) -> None:
        self.popups.refresh_group_list()

    def _place_groups_beside(self) -> None:
        self.popups.place_groups_beside()

    def _show_groups_beside(self) -> None:
        self.popups.show_groups_beside()

    def _hide_groups_beside(self) -> None:
        self.popups.hide_groups_beside()

    def _show_group_panel(self) -> None:
        self.popups.show_group_panel()

    def _on_group_panel_closed(self) -> None:
        self.popups.on_group_panel_closed()

    def _standalone_items(self, mode: PopupMode) -> bool:
        return self.popups.standalone_items(mode)

    def _refresh_standalone(self, mode: PopupMode) -> None:
        self.popups.refresh_standalone(mode)

    def _fit_schedule_width(self, panel: DropdownPanel) -> None:
        self.popups.fit_schedule_width(panel)

    def _refresh_container_list(self) -> None:
        self.popups.refresh_standalone(PopupMode.CONTAINERS_ONLY)

    def _show_container_list(self) -> None:
        self.popups.show_standalone(PopupMode.CONTAINERS_ONLY)

    def _show_schedule_list(self) -> None:
        self.popups.show_standalone(PopupMode.SCHEDULES_ONLY)

    def _show_standalone(self, mode: PopupMode) -> None:
        self.popups.show_standalone(mode)

    def _hide_standalone(self) -> None:
        self.popups.hide_standalone()

    def _hide_container_list(self) -> None:
        self.popups.hide_standalone()

    def _on_standalone_closed(self, panel: DropdownPanel) -> None:
        self.popups.on_standalone_closed(panel)

    def _side_for(self, panel: DropdownPanel) -> SideMenu:
        return self.popups.side_for(panel)

    def _on_standalone_enter(self, panel: DropdownPanel) -> None:
        self.popups.on_standalone_enter(panel)

    def _on_standalone_leave(self, panel: DropdownPanel) -> None:
        self.popups.on_standalone_leave(panel)

    def _dropdown_settled_open(self) -> bool:
        return self.popups.dropdown_settled_open()

    def _show_main_popup(self) -> None:
        self.popups.show_main_popup()

    def _apply_pinned_state(self) -> None:
        self.popups.apply_pinned_state()

    def _follow_trigger(self) -> None:
        self.popups.follow_trigger()

    def _on_arrow_drag_started(self) -> None:
        self.popups.on_arrow_drag_started()

    def _on_arrow_drag_finished(self) -> None:
        self.popups.on_arrow_drag_finished()

    def _on_trigger_enter(self) -> None:
        self.popups.on_trigger_enter()

    def _on_trigger_leave(self) -> None:
        self.popups.on_trigger_leave()

    def _on_dropdown_enter(self) -> None:
        self.popups.on_dropdown_enter()

    def _on_dropdown_leave(self) -> None:
        self.popups.on_dropdown_leave()

    def _on_group_enter(self) -> None:
        self.popups.on_group_enter()

    def _on_group_leave(self) -> None:
        self.popups.on_group_leave()

    def _on_side_enter(self, menu: SideMenu) -> None:
        self.popups.on_side_enter(menu)

    def _on_container_leave(self) -> None:
        self.popups.on_container_leave()

    def _on_execute_leave(self) -> None:
        self.popups.on_execute_leave()

    def _container_prefer_right(self) -> bool:
        return self.popups.container_prefer_right()

    def _execute_prefer_right(self) -> bool:
        return self.popups.execute_prefer_right()

    def _place_container(self) -> None:
        self.popups.place_container()

    def _place_execute_members(self) -> None:
        self.popups.place_execute_members()

    def _on_container_list_reordered(self, tokens: list[str]) -> None:
        self.drag.on_container_list_reordered(tokens)

    def _show_container_menu(self, group_id: str, *, force: bool = False) -> None:
        self.popups.show_container_menu(group_id, force=force)

    def _show_execute_members(self, group_id: str, *, force: bool = False) -> None:
        self.popups.show_execute_members(group_id, force=force)

    def _refresh_open_container(self) -> None:
        self.popups.refresh_open_container()

    def _refresh_open_execute(self) -> None:
        self.popups.refresh_open_execute()

    def _refresh_open_list(self) -> None:
        self.popups.refresh_open_list()

    def _sync_groups_after_change(self) -> None:
        self.popups.sync_groups_after_change()

    def _on_tray_clicked(self) -> None:
        self.popups.on_tray_clicked()

    # ------------------------------------------------------------- dragging

    def _find_drop_peer(self, global_pos: QPoint) -> DropdownPanel | None:
        return self.drag.find_drop_peer(global_pos)

    def _dest_visible(self, target_key: str) -> list[str] | None:
        return self.drag.dest_visible(target_key)

    def _on_external_drop(
        self, launcher_id: str, source_key: str, target_key: str, index: int
    ) -> None:
        self.drag.on_external_drop(launcher_id, source_key, target_key, index)

    def _on_drag_finished(self) -> None:
        self.drag.on_drag_finished()

    def _on_container_reordered(self, ordered_ids: list[str]) -> None:
        self.drag.on_container_reordered(ordered_ids)

    def _on_execute_members_reordered(self, ordered_ids: list[str]) -> None:
        self.drag.on_execute_members_reordered(ordered_ids)

    # ------------------------------------------------------------ launching

    def _notify(self, title: str, text: str) -> None:
        self.launches.notify(title, text)

    def _on_launch(self, launcher: Launcher) -> None:
        self.launches.on_launch(launcher)

    def _on_group_launch(self, row: Launcher) -> None:
        self.launches.on_group_launch(row)

    def _on_schedule_click(self, row: Launcher) -> None:
        self.launches.on_schedule_click(row)

    def _run_scheduled(self, group: Group) -> None:
        self.launches.run_scheduled(group)

    def _start_group(self, group: Group, notice: str) -> None:
        self.launches.start_group(group, notice)

    # -------------------------------------------------------------- dialogs

    @property
    def help_window(self) -> HelpWindow | None:
        return self.dialogs.help_window

    @help_window.setter
    def help_window(self, window: HelpWindow | None) -> None:
        self.dialogs.help_window = window

    def _confirm_delete(self, title: str, name: str) -> bool:
        return self.dialogs.confirm_delete(title, name)

    def show_add_dialog(self, existing: Launcher | None = None) -> None:
        self.dialogs.show_add_dialog(existing)

    def _on_edit_launcher(self, launcher: Launcher) -> None:
        self.dialogs.on_edit_launcher(launcher)

    def _on_delete_launcher(self, launcher: Launcher) -> None:
        self.dialogs.on_delete_launcher(launcher)

    def show_manager_dialog(self) -> None:
        self.dialogs.show_manager_dialog()

    def show_group_dialog(self, existing: Group | None = None, *, scheduled: bool = False) -> None:
        self.dialogs.show_group_dialog(existing, scheduled=scheduled)

    def show_group_manager(self) -> None:
        self.dialogs.show_group_manager()

    def show_schedule_manager(self) -> None:
        self.dialogs.show_schedule_manager()

    def _on_group_edit(self, row: Launcher) -> None:
        self.dialogs.on_group_edit(row)

    def _on_group_delete(self, row: Launcher) -> None:
        self.dialogs.on_group_delete(row)

    def show_container_dialog(self, existing: ContainerGroup | None = None) -> None:
        self.dialogs.show_container_dialog(existing)

    def show_container_manager(self) -> None:
        self.dialogs.show_container_manager()

    def _on_container_edit(self, group_id: str) -> None:
        self.dialogs.on_container_edit(group_id)

    def _on_container_delete(self, group_id: str) -> None:
        self.dialogs.on_container_delete(group_id)

    def show_help(self) -> None:
        self.dialogs.show_help()

    def _report_load_problems(self) -> None:
        self.dialogs.report_load_problems()

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
        self.dialogs.apply_theme()
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
