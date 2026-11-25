"""Cross-panel drag-and-drop and row reorder coordination for RunnerController."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint

from .moves import container_token, merge_visible_order
from .ui.dropdown import DropdownPanel, SubmenuButton
from .ui.launch_button import LaunchButton

if TYPE_CHECKING:
    from .controller import RunnerController


class DragCoordinator:
    """Routes cross-menu drags and persists row reorders across Runner's lists."""

    def __init__(self, controller: RunnerController) -> None:
        self._ctl = controller

    def on_container_list_reordered(self, tokens: list[str]) -> None:
        """Container Groups was reordered by drag. Save it as the container order."""
        ctl = self._ctl
        prefix = container_token("")
        moved = [token[len(prefix) :] for token in tokens if token.startswith(prefix)]
        # A filter can hide rows. Those keep their places; only the shown ones move.
        shown = set(moved)
        current = [group.id for group in ctl.cfg.config.container_groups]
        ctl.cfg.reorder_container_groups(
            merge_visible_order([(gid, gid in shown) for gid in current], moved)
        )

    def find_drop_peer(self, global_pos: QPoint) -> DropdownPanel | None:
        """Open the menu under the pointer, then return the list that contains it."""
        ctl = self._ctl
        source = next(
            (
                panel
                for panel in (
                    ctl.dropdown,
                    ctl.container_panel,
                    ctl.execute_panel,
                    ctl.group_panel,
                )
                if panel.is_dragging()
            ),
            None,
        )
        ctl._cancel_hide()
        ctl.container_menu.timer.stop()
        ctl.execute_menu.timer.stop()
        # A container row only reorders inside the main list.
        if source is ctl.dropdown and source.dragging_submenu():
            if ctl.dropdown.isVisible() and ctl.dropdown.frameGeometry().contains(global_pos):
                return ctl.dropdown
            return None
        if (
            source is not ctl.execute_panel
            and ctl.group_panel.isVisible()
            and not ctl.group_panel.is_dragging()
        ):
            row = ctl.group_panel.row_at(global_pos)
            if isinstance(row, LaunchButton):
                ctl._show_execute_members(row.launcher.id)
        if source is not ctl.container_panel and ctl.dropdown.isVisible():
            row = ctl.dropdown.row_at(global_pos)
            if isinstance(row, SubmenuButton):
                ctl._show_container_menu(row.item_id)
        for panel in (ctl.execute_panel, ctl.container_panel, ctl.dropdown, ctl.group_panel):
            if panel.isVisible() and panel.frameGeometry().contains(global_pos):
                return panel
        return None

    def dest_visible(self, target_key: str) -> list[str] | None:
        ctl = self._ctl
        if target_key == "main":
            return ctl.dropdown.row_tokens()
        kind, _, ident = target_key.partition(":")
        if (
            kind == "container"
            and ctl.container_menu.open_id == ident
            and ctl.container_panel.isVisible()
        ):
            return ctl.container_panel.visible_launcher_ids()
        if (
            kind == "execute"
            and ctl.execute_menu.open_id == ident
            and ctl.execute_panel.isVisible()
        ):
            return ctl.execute_panel.visible_launcher_ids()
        return None

    def on_external_drop(
        self, launcher_id: str, source_key: str, target_key: str, index: int
    ) -> None:
        from .controller import fill_main_dropdown

        ctl = self._ctl
        visible = self.dest_visible(target_key)
        ctl.cfg.move_launcher(launcher_id, source_key, target_key, index, visible)
        fill_main_dropdown(ctl.dropdown, ctl.cfg)
        if ctl.container_menu.open_id:
            ctl._show_container_menu(ctl.container_menu.open_id, force=True)
        if ctl.execute_menu.open_id:
            ctl._show_execute_members(ctl.execute_menu.open_id, force=True)

    def on_drag_finished(self) -> None:
        ctl = self._ctl
        ctl.container_menu.hide_if_left()
        ctl.execute_menu.hide_if_left()
        # The mouse grab swallows leave events. Keep whichever list is under
        # the pointer, and hide the session when the pointer is over none of them.
        if ctl._pointer_over_any():
            ctl._cancel_hide()
            return
        if ctl._should_hide_on_leave():
            ctl._schedule_hide()

    def on_container_reordered(self, ordered_ids: list[str]) -> None:
        if self._ctl.container_menu.open_id:
            self._ctl.cfg.reorder_container_members(self._ctl.container_menu.open_id, ordered_ids)

    def on_execute_members_reordered(self, ordered_ids: list[str]) -> None:
        if self._ctl.execute_menu.open_id:
            self._ctl.cfg.reorder_group_members(self._ctl.execute_menu.open_id, ordered_ids)
