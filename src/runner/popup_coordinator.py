"""Popup lists, hover/fade timers, side menus, and stacking for RunnerController."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QWidget

from .config import ConfigManager, Launcher
from .moves import member_launchers, visible_main_tokens
from .schedule import format_when, group_next_run
from .ui.dropdown import DropdownPanel

if TYPE_CHECKING:
    from .controller import RunnerController

# The schedules list grows to fit a name and its next run, up to this width.
SCHEDULE_LIST_MAX_W = 460
# A row's text inset, the list's frame, and room for its scrollbar.
SCHEDULE_ROW_PADDING = 64


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


class PopupCoordinator:
    """Manages popup modes, hover/fade lifecycles, side menus, and window stacking."""

    def __init__(self, controller: RunnerController) -> None:
        self._ctl = controller

    # ------------------------------------------------------------ mode & state

    def groups_beside_enabled(self) -> bool:
        return bool(self._ctl.settings.show_groups)

    def groups_only(self) -> bool:
        return self._ctl.mode is PopupMode.GROUPS_ONLY

    def containers_only(self) -> bool:
        return self._ctl.mode is PopupMode.CONTAINERS_ONLY

    def schedules_only(self) -> bool:
        return self._ctl.mode is PopupMode.SCHEDULES_ONLY

    def one_list_only(self) -> bool:
        """A list opened on its own from the arrow menu is showing instead of the main popup."""
        return self._ctl.mode is not PopupMode.MAIN

    def standalone_panel(self) -> DropdownPanel | None:
        """The container or schedules list, when the arrow menu opened it on its own."""
        return self._ctl._standalone.get(self._ctl.mode)

    def all_lists(self) -> tuple[DropdownPanel, ...]:
        ctl = self._ctl
        return (
            ctl.dropdown,
            ctl.group_panel,
            ctl.container_list,
            ctl.schedule_list,
            ctl.container_panel,
            ctl.execute_panel,
        )

    def container_host(self) -> DropdownPanel:
        """The list whose container rows open the container's launchers."""
        return self._ctl.container_list if self.containers_only() else self._ctl.dropdown

    def execute_host(self) -> DropdownPanel:
        """The list whose group rows open that group's launchers."""
        return self._ctl.schedule_list if self.schedules_only() else self._ctl.group_panel

    def pointer_over_any(self, *, trigger: bool = True) -> bool:
        panels = list(self.all_lists())
        if trigger:
            panels.append(self._ctl.trigger)
        return any(_pointer_over(widget) for widget in panels)

    def any_drag(self) -> bool:
        return any(panel.is_dragging() for panel in self.all_lists())

    def keep_arrow_on_top(self, *panels: DropdownPanel) -> None:
        """The arrow stays above the lists that open from it.

        A greeting that is showing sits between them: its rim hugs the arrow,
        and its bubble keeps clear of the lists. On macOS only the raise
        orders these windows; stackUnder() is for the other platforms.
        """
        ctl = self._ctl
        ctl.trigger.raise_()
        for panel in panels:
            panel.stackUnder(ctl.trigger)
        ctl.greeting.stack_with(ctl.trigger, self.open_lists())

    def open_lists(self) -> list[DropdownPanel]:
        return [panel for panel in self.all_lists() if panel.isVisible()]

    def make_room_for_dialog(self) -> None:
        """A dialog is opening: close the lists that are only open on hover.

        The pointer is about to leave them for the dialog anyway, and the
        dialog would open over them. A pinned launcher list stays, and the
        dialog opens clear of it.
        """
        ctl = self._ctl
        if ctl._arrow_dragging or not ctl.trigger.isVisible():
            return
        ctl.hide_timer.stop()
        ctl.container_menu.hide()
        ctl.execute_menu.hide()
        if self.one_list_only():
            for panel in (ctl.group_panel, *ctl._standalone.values()):
                if panel.isVisible():
                    panel.force_hide()  # its close handler restores a pinned list
            return
        if ctl.settings.pinned_open:
            return
        for panel in (ctl.dropdown, ctl.group_panel):
            if panel.isVisible():
                panel.force_hide()

    def restack_after_activation(self) -> None:
        ctl = self._ctl
        if ctl.trigger.isVisible() and not ctl._arrow_dragging:
            self.keep_arrow_on_top()

    # -------------------------------------------------------------- hiding

    def schedule_hide(self) -> None:
        self._ctl.hide_timer.start()

    def cancel_hide(self) -> None:
        self._ctl.hide_timer.stop()
        for panel in self.all_lists():
            panel.cancel_hide()

    def should_hide_on_leave(self) -> bool:
        return self.one_list_only() or not self._ctl.settings.pinned_open

    def collapse_open_lists(self) -> None:
        """Close every open list now.

        A fade stays under the pointer, and the hover that is already there
        cancels it. That happens when the launched app was already focused,
        so the pointer never leaves. A selection hides the lists outright.
        """
        ctl = self._ctl
        if ctl.settings.pinned_open:
            return
        ctl.container_menu.hide()
        ctl.execute_menu.hide()
        if ctl.dropdown.isVisible():
            ctl.dropdown.force_hide()
        if ctl.group_panel.isVisible():
            ctl.group_panel.force_hide()
        if ctl.container_list.isVisible():
            ctl.container_list.force_hide()

    def do_hide(self) -> None:
        ctl = self._ctl
        if self.pointer_over_any():
            return
        _decay(ctl.container_panel)
        _decay(ctl.execute_panel)
        if self.groups_only():
            ctl.group_panel.start_hide_animation()
            return
        standalone = self.standalone_panel()
        if standalone is not None:
            standalone.start_hide_animation()
            return
        pinned = ctl.settings.pinned_open
        if (
            not pinned
            and self.groups_beside_enabled()
            and ctl.locked_pair.close_visible([ctl.dropdown, ctl.group_panel])
        ):
            return
        if ctl.group_panel.isVisible():
            ctl.group_panel.start_hide_animation()
        if not pinned:
            ctl.dropdown.start_hide_animation()

    # ---------------------------------------------------- groups list beside

    def refresh_group_list(self) -> None:
        ctl = self._ctl
        rows = [
            Launcher(id=group.id, name=group.name, command="")
            for group in ctl._execute_groups()
        ]
        ctl.group_panel.rebuild_buttons(rows)
        if ctl.group_panel.isVisible():
            ctl.group_panel.update_height_for_content()

    def place_groups_beside(self) -> None:
        self._ctl.group_panel.position_beside(self._ctl.dropdown, self._ctl.trigger)

    def show_groups_beside(self) -> None:
        """The launcher list stays. Groups sit beside it, toward the middle of the screen.

        An empty group list stays hidden.
        """
        ctl = self._ctl
        if self.groups_only() or not self.groups_beside_enabled():
            return
        if not ctl._execute_groups():
            self.hide_groups_beside()
            return
        self.refresh_group_list()
        ctl.group_panel.use_position_hook(self.place_groups_beside)
        if ctl.locked_pair.is_presented():
            ctl.locked_pair.reposition([ctl.dropdown, ctl.group_panel])
        elif ctl.group_panel.isVisible():
            ctl.group_panel.ensure_visible_and_sized()
        else:
            ctl.group_panel.start_show_animation()
        self.keep_arrow_on_top(ctl.dropdown, ctl.group_panel)

    def hide_groups_beside(self) -> None:
        ctl = self._ctl
        if self.groups_only():
            return
        ctl.group_panel.use_position_hook(None)
        if ctl.group_panel.isVisible():
            ctl.group_panel.force_hide()

    def show_group_panel(self) -> None:
        """The execute-groups list on its own, from the arrow menu."""
        ctl = self._ctl
        ctl.container_menu.hide()
        ctl.execute_menu.hide()
        self.hide_standalone()
        if not ctl._execute_groups():
            ctl.mode = PopupMode.MAIN
            self.hide_groups_beside()
            return
        ctl.mode = PopupMode.GROUPS_ONLY
        self.cancel_hide()
        ctl.group_panel.use_position_hook(None)
        if ctl.dropdown.isVisible():
            ctl.dropdown.force_hide()
        self.refresh_group_list()
        ctl.group_panel.position_adjacent(ctl.trigger)
        if ctl.group_panel.isVisible():
            ctl.group_panel.ensure_visible_and_sized()
        else:
            ctl.group_panel.start_show_animation()
        self.keep_arrow_on_top(ctl.group_panel)

    def on_group_panel_closed(self) -> None:
        # A hide that was already running can finish after the list is shown again.
        # A list closed by an arrow drag opens again where the arrow lands.
        ctl = self._ctl
        if ctl.group_panel.isVisible() or self.standalone_panel() is not None or ctl._arrow_dragging:
            return
        ctl.mode = PopupMode.MAIN
        if ctl.settings.pinned_open:
            self.apply_pinned_state()

    # ------------------------------- container groups and schedules, alone

    def standalone_items(self, mode: PopupMode) -> bool:
        """Whether that list has anything to show."""
        if mode is PopupMode.CONTAINERS_ONLY:
            return bool(self._ctl.cfg.config.container_groups)
        return bool(self._ctl._scheduled_groups())

    def refresh_standalone(self, mode: PopupMode) -> None:
        ctl = self._ctl
        panel = ctl._standalone[mode]
        if mode is PopupMode.CONTAINERS_ONLY:
            panel.set_submenu_items(
                [(group.id, group.name) for group in ctl.cfg.config.container_groups]
            )
            panel.rebuild_buttons([])
        else:
            now = datetime.now()
            rows = []
            for group in ctl._scheduled_groups():
                upcoming = group_next_run(group, now)
                when = (
                    f"next {format_when(upcoming, with_year=upcoming.year != now.year)}"
                    if upcoming
                    else "no upcoming runs"
                )
                rows.append(Launcher(id=group.id, name=f"{group.name}  ·  {when}", command=""))
            panel.rebuild_buttons(rows)
            self.fit_schedule_width(panel)
        if panel.isVisible():
            panel.update_height_for_content()

    def fit_schedule_width(self, panel: DropdownPanel) -> None:
        """Wide enough for a name and its next run, between the list width and SCHEDULE_LIST_MAX_W."""
        base = self._ctl.settings.dropdown_width
        buttons = panel._launch_buttons()
        if buttons:
            metrics = buttons[0].fontMetrics()
            need = max(metrics.horizontalAdvance(b.launcher.name) for b in buttons) + SCHEDULE_ROW_PADDING
        else:
            need = base
        panel.setFixedWidth(max(base, min(need, SCHEDULE_LIST_MAX_W)))

    def show_standalone(self, mode: PopupMode) -> None:
        ctl = self._ctl
        ctl.container_menu.hide()
        ctl.execute_menu.hide()
        if not self.standalone_items(mode):
            self.hide_standalone()
            return
        panel = ctl._standalone[mode]
        ctl.mode = mode
        self.cancel_hide()
        for other in (ctl.dropdown, ctl.group_panel, *ctl._standalone.values()):
            if other is panel:
                continue
            other.use_position_hook(None)
            if other.isVisible():
                other.force_hide()
        self.refresh_standalone(mode)
        panel.position_adjacent(ctl.trigger)
        if panel.isVisible() and not panel.is_closing():
            panel.ensure_visible_and_sized()
        else:
            panel.start_show_animation()
        self.keep_arrow_on_top(panel)

    def hide_standalone(self) -> None:
        """Back to the main popup's mode. The pinned list returns when pinned."""
        ctl = self._ctl
        panel = self.standalone_panel()
        ctl.mode = PopupMode.MAIN
        if panel is not None and panel.isVisible():
            panel.force_hide()
        elif panel is not None and ctl.settings.pinned_open:
            self.apply_pinned_state()

    def on_standalone_closed(self, panel: DropdownPanel) -> None:
        # A hide that was already running can finish after the list is shown again.
        ctl = self._ctl
        if panel.isVisible() or self.standalone_panel() is not panel or ctl._arrow_dragging:
            return
        ctl.container_menu.hide()
        ctl.execute_menu.hide()
        ctl.mode = PopupMode.MAIN
        if ctl.settings.pinned_open:
            self.apply_pinned_state()

    def side_for(self, panel: DropdownPanel) -> SideMenu:
        ctl = self._ctl
        return ctl.container_menu if panel is ctl.container_list else ctl.execute_menu

    def on_standalone_enter(self, panel: DropdownPanel) -> None:
        self.cancel_hide()
        self.side_for(panel).timer.stop()
        if panel.is_closing() and self.standalone_panel() is panel:
            panel.cancel_close()

    def on_standalone_leave(self, panel: DropdownPanel) -> None:
        if not panel.isVisible():
            return  # a late leave from a list that is already closed
        side = self.side_for(panel)
        if _pointer_over(side.panel):
            return
        side.schedule_hide()
        if self.standalone_panel() is panel:
            self.schedule_hide()

    # ---------------------------------------------------------- main popup

    def dropdown_settled_open(self) -> bool:
        """True when the launcher list is already fully open on its own."""
        ctl = self._ctl
        return (
            ctl.dropdown.isVisible()
            and not ctl.dropdown.is_closing()
            and ctl.dropdown.windowOpacity() >= 0.95
            and not ctl.locked_pair.is_presented()
        )

    def show_main_popup(self) -> None:
        """Open the launcher list, where container group rows live.

        Arrow hover with execute groups showing drives both lists from one
        clock. A list that is already fully open, such as while pinned, stays
        put instead of collapsing back to the start of that clock.
        """
        ctl = self._ctl
        ctl.mode = PopupMode.MAIN
        self.cancel_hide()
        ctl.container_menu.hide()
        ctl.execute_menu.hide()
        for panel in ctl._standalone.values():
            if panel.isVisible():
                panel.force_hide()
        fill_main_dropdown(ctl.dropdown, ctl.cfg)
        ctl.dropdown.position_adjacent(ctl.trigger)
        groups_too = self.groups_beside_enabled() and bool(ctl._execute_groups())
        if groups_too and (ctl.locked_pair.is_presented() or not self.dropdown_settled_open()):
            self.refresh_group_list()
            ctl.group_panel.use_position_hook(self.place_groups_beside)
            ctl.locked_pair.open([ctl.dropdown, ctl.group_panel])
        else:
            if not ctl.dropdown.isVisible() or ctl.dropdown.is_closing():
                ctl.dropdown.start_show_animation()
            if groups_too:
                self.show_groups_beside()
            else:
                self.hide_groups_beside()
        self.keep_arrow_on_top(ctl.dropdown, ctl.group_panel)

    def apply_pinned_state(self) -> None:
        ctl = self._ctl
        if self.one_list_only():
            return
        if ctl._arrow_dragging:
            return  # the drop reopens a pinned list where the arrow lands
        if ctl.settings.pinned_open:
            ctl.dropdown.position_adjacent(ctl.trigger)
            ctl.dropdown.cancel_hide()
            ctl.dropdown.update_height_for_content()
            if not ctl.dropdown.isVisible():
                ctl.dropdown.start_show_animation()
            else:
                ctl.dropdown.update_height_for_content()
            self.keep_arrow_on_top(ctl.dropdown)
            if self.groups_beside_enabled():
                self.show_groups_beside()
        else:
            ctl.dropdown.force_hide()
            ctl.container_menu.hide()
            ctl.execute_menu.hide()
            self.hide_groups_beside()

    def follow_trigger(self) -> None:
        """Keep whichever list is open beside the arrow."""
        ctl = self._ctl
        if ctl._arrow_dragging:
            return
        if self.groups_only() and ctl.group_panel.isVisible():
            ctl.group_panel.use_position_hook(None)
            ctl.group_panel.position_adjacent(ctl.trigger)
            ctl.group_panel.ensure_visible_and_sized()
            self.keep_arrow_on_top(ctl.group_panel)
            return
        standalone = self.standalone_panel()
        if standalone is not None:
            if standalone.isVisible():
                standalone.position_adjacent(ctl.trigger)
                standalone.ensure_visible_and_sized()
                self.keep_arrow_on_top(standalone)
            return
        if ctl.locked_pair.is_presented():
            if self.groups_beside_enabled() and ctl._execute_groups():
                self.show_groups_beside()
            self.keep_arrow_on_top(ctl.dropdown, ctl.group_panel)
            return
        pinned = ctl.settings.pinned_open
        if not ctl.dropdown.isVisible() and not pinned:
            return
        ctl.dropdown.position_adjacent(ctl.trigger)
        if pinned:
            ctl.dropdown.ensure_visible_and_sized()
        self.keep_arrow_on_top(ctl.dropdown)
        if self.groups_beside_enabled() and (ctl.group_panel.isVisible() or pinned):
            self.show_groups_beside()

    # ------------------------------------------------------- hover handlers

    def on_arrow_drag_started(self) -> None:
        """Moving the arrow closes every list at once, pinned or not."""
        ctl = self._ctl
        ctl._arrow_dragging = True
        ctl.hide_timer.stop()
        ctl.container_menu.hide()
        ctl.execute_menu.hide()
        for panel in self.all_lists():
            if panel.isVisible():
                panel.force_hide()

    def on_arrow_drag_finished(self) -> None:
        """The lists open again where the arrow was dropped, as a hover opens them."""
        ctl = self._ctl
        ctl._arrow_dragging = False
        if ctl.settings.pinned_open:
            self.apply_pinned_state()
        self.on_trigger_enter()
        # A release noticed late can come with the pointer elsewhere. Then no
        # leave will arrive to close the lists, so start the usual fade now.
        if not self.pointer_over_any() and self.should_hide_on_leave():
            self.schedule_hide()

    def on_trigger_enter(self) -> None:
        ctl = self._ctl
        if ctl._arrow_dragging:
            return
        self.cancel_hide()
        ctl.container_menu.hide()
        ctl.execute_menu.hide()
        if self.groups_only():
            ctl.group_panel.position_adjacent(ctl.trigger)
            if ctl.group_panel.is_closing() or not ctl.group_panel.isVisible():
                self.show_group_panel()
            self.keep_arrow_on_top(ctl.group_panel)
            return
        standalone = self.standalone_panel()
        if standalone is not None:
            standalone.position_adjacent(ctl.trigger)
            if standalone.is_closing() or not standalone.isVisible():
                self.show_standalone(ctl.mode)
            self.keep_arrow_on_top(standalone)
            return
        self.show_main_popup()

    def on_trigger_leave(self) -> None:
        # Moving from the arrow onto a list must not start a hide.
        # The list's own leave collapses it.
        if self.pointer_over_any(trigger=False):
            return
        if self.should_hide_on_leave():
            self.schedule_hide()

    def on_dropdown_enter(self) -> None:
        self.cancel_hide()
        if self._ctl.dropdown.is_closing():
            self._ctl.dropdown.cancel_close()

    def on_dropdown_leave(self) -> None:
        # A list that was just closed can still report the pointer leaving.
        # That must not start a hide for the list opened in its place.
        ctl = self._ctl
        if not ctl.dropdown.isVisible():
            return
        if (
            _pointer_over(ctl.group_panel)
            or _pointer_over(ctl.container_panel)
            or _pointer_over(ctl.execute_panel)
        ):
            return
        ctl.container_menu.schedule_hide()
        if not ctl.settings.pinned_open:
            self.schedule_hide()

    def on_group_enter(self) -> None:
        ctl = self._ctl
        self.cancel_hide()
        ctl.execute_menu.timer.stop()
        if ctl.group_panel.is_closing() and (self.groups_only() or self.groups_beside_enabled()):
            ctl.group_panel.cancel_close()

    def on_group_leave(self) -> None:
        ctl = self._ctl
        if not ctl.group_panel.isVisible():
            return  # a late leave from a list that is already closed
        if _pointer_over(ctl.execute_panel):
            return
        ctl.execute_menu.schedule_hide()
        if self.groups_only() or (self.groups_beside_enabled() and not ctl.settings.pinned_open):
            self.schedule_hide()

    def on_side_enter(self, menu: SideMenu) -> None:
        self.cancel_hide()
        menu.timer.stop()
        if menu.panel.is_closing():
            menu.panel.cancel_close()

    def on_container_leave(self) -> None:
        ctl = self._ctl
        ctl.container_menu.schedule_hide()
        if (
            _pointer_over(ctl.dropdown)
            or _pointer_over(ctl.container_list)
            or _pointer_over(ctl.trigger)
            or _pointer_over(ctl.execute_panel)
        ):
            return
        if self.should_hide_on_leave():
            self.schedule_hide()

    def on_execute_leave(self) -> None:
        ctl = self._ctl
        ctl.execute_menu.schedule_hide()
        if (
            _pointer_over(ctl.group_panel)
            or _pointer_over(ctl.schedule_list)
            or _pointer_over(ctl.dropdown)
            or _pointer_over(ctl.trigger)
            or _pointer_over(ctl.container_panel)
        ):
            return
        if self.should_hide_on_leave():
            self.schedule_hide()

    # ------------------------------------------------------------ side menus

    def container_prefer_right(self) -> bool:
        """Open on the side opposite the execute-groups list when that list is up."""
        ctl = self._ctl
        if self.containers_only():
            return True
        return not (ctl.group_panel.isVisible() and ctl.group_panel.x() >= ctl.dropdown.x())

    def execute_prefer_right(self) -> bool:
        """Open away from the main list when both lists are on screen."""
        ctl = self._ctl
        if self.schedules_only():
            return True
        return not (ctl.dropdown.isVisible() and ctl.dropdown.x() >= ctl.group_panel.x())

    def place_container(self) -> None:
        button = self._ctl.container_menu.anchor()
        if button is not None:
            self._ctl.container_panel.position_next_to(
                self.container_host(), button, prefer_right=self.container_prefer_right()
            )

    def place_execute_members(self) -> None:
        button = self._ctl.execute_menu.anchor()
        if button is not None:
            self._ctl.execute_panel.position_next_to(
                self.execute_host(), button, prefer_right=self.execute_prefer_right()
            )

    def show_container_menu(self, group_id: str, *, force: bool = False) -> None:
        ctl = self._ctl
        menu, panel = ctl.container_menu, ctl.container_panel
        # This panel is the source while a launcher is dragged out of it.
        if panel.is_dragging():
            return
        # A container row being dragged only changes place. Opening another
        # container's submenu under it would offer a drop it cannot make.
        if any(lst.dragging_submenu() for lst in (ctl.dropdown, ctl.container_list)):
            menu.hide()
            return
        host = self.container_host()
        group = ctl._container_by_id(group_id)
        button = host.submenu_button(group_id) if group is not None else None
        if not host.isVisible() or button is None or not button.isVisible():
            menu.hide()
            return
        menu.timer.stop()
        already = not force and menu.is_open_for(group_id)
        menu.open_id = group_id
        panel.set_drag_source_key(f"container:{group_id}")
        panel.set_heading(group.name)
        panel.use_position_hook(self.place_container)
        panel.cancel_hide()
        if already:
            return
        panel.rebuild_buttons(member_launchers(group.members, ctl.cfg.config.launchers))
        if panel.isVisible() and not panel.is_closing():
            panel.ensure_visible_and_sized()
        else:
            panel.start_show_animation(focus=not self.any_drag())
        self.keep_arrow_on_top(host, panel)

    def show_execute_members(self, group_id: str, *, force: bool = False) -> None:
        ctl = self._ctl
        menu, panel = ctl.execute_menu, ctl.execute_panel
        host = self.execute_host()
        if panel.is_dragging() or host.is_dragging():
            return
        group = ctl._group_by_id(group_id)
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
        panel.use_position_hook(self.place_execute_members)
        panel.cancel_hide()
        if already:
            return
        panel.rebuild_buttons(member_launchers(group.members, ctl.cfg.config.launchers))
        if panel.isVisible() and not panel.is_closing():
            panel.ensure_visible_and_sized()
        else:
            panel.start_show_animation(focus=not self.any_drag())
        self.keep_arrow_on_top(host, panel)

    def refresh_open_container(self) -> None:
        ctl = self._ctl
        if ctl.container_menu.open_id and ctl.container_panel.isVisible():
            self.show_container_menu(ctl.container_menu.open_id, force=True)

    def refresh_open_execute(self) -> None:
        ctl = self._ctl
        if ctl.execute_menu.open_id and ctl.execute_panel.isVisible():
            self.show_execute_members(ctl.execute_menu.open_id, force=True)

    def refresh_open_list(self) -> None:
        ctl = self._ctl
        fill_main_dropdown(ctl.dropdown, ctl.cfg)
        standalone = self.standalone_panel()
        if standalone is not None:
            if not self.standalone_items(ctl.mode):
                self.hide_standalone()
            else:
                self.refresh_standalone(ctl.mode)
                if standalone.isVisible():
                    standalone.position_adjacent(ctl.trigger)
                    standalone.ensure_visible_and_sized()
        self.refresh_open_container()
        self.refresh_open_execute()
        if ctl.settings.pinned_open:
            self.apply_pinned_state()

    def sync_groups_after_change(self) -> None:
        """Keep an open groups list in step with add, edit, and delete.

        The member list closes when its execute group is gone. With no groups
        left, the list hides.
        """
        ctl = self._ctl
        ctl.scheduler.refresh()
        if ctl.execute_menu.open_id and ctl._group_by_id(ctl.execute_menu.open_id) is None:
            ctl.execute_menu.hide()
        elif ctl.execute_menu.open_id:
            self.refresh_open_execute()
        if self.schedules_only():
            self.refresh_open_list()
            return
        if self.groups_only():
            if not ctl._execute_groups():
                ctl.group_panel.force_hide()
                return
            self.refresh_group_list()
            if ctl.group_panel.isVisible():
                ctl.group_panel.position_adjacent(ctl.trigger)
                ctl.group_panel.ensure_visible_and_sized()
            return
        if self.groups_beside_enabled() and (
            ctl.group_panel.isVisible() or ctl.dropdown.isVisible() or ctl.settings.pinned_open
        ):
            self.show_groups_beside()

    def on_tray_clicked(self) -> None:
        ctl = self._ctl
        ctl.container_menu.hide()
        ctl.execute_menu.hide()
        if self.groups_only():
            ctl.group_panel.force_hide()
        if self.standalone_panel() is not None:
            self.hide_standalone()
        ctl.dropdown.position_adjacent(ctl.trigger)
        fill_main_dropdown(ctl.dropdown, ctl.cfg)
        if ctl.settings.pinned_open:
            ctl.dropdown.ensure_visible_and_sized()
        else:
            ctl.dropdown.start_show_animation()
        self.keep_arrow_on_top(ctl.dropdown)
