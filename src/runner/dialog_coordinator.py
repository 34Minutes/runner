"""Dialog and message-box flows for RunnerController."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from .config import ContainerGroup, Group, Launcher
from .ui.add_dialog import AddEditDialog
from .ui.container_dialog import ContainerDialog
from .ui.container_manager import ContainerManagerDialog
from .ui.group_dialog import GroupDialog
from .ui.group_manager import GroupManagerDialog, ScheduleManagerDialog
from .ui.help_dialog import HelpWindow
from .ui.manager_dialog import ManagerDialog
from .ui.stay_on_top import question as stay_on_top_question
from .ui.stay_on_top import warning as stay_on_top_warning

if TYPE_CHECKING:
    from .controller import RunnerController

# Shown at most this many config problems in the warning. The rest are counted.
_MAX_PROBLEMS_SHOWN = 12


class DialogCoordinator:
    """Runs Add, Edit, Manage, Help, and confirmation dialogs for the controller."""

    def __init__(self, controller: RunnerController) -> None:
        self._ctl = controller
        self.help_window: HelpWindow | None = None

    def confirm_delete(self, title: str, name: str) -> bool:
        reply = stay_on_top_question(
            self._ctl.trigger,
            title,
            f"Delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def show_add_dialog(self, existing: Launcher | None = None) -> None:
        from .controller import fill_main_dropdown

        ctl = self._ctl
        dialog = AddEditDialog(existing, ctl.trigger, cfg=ctl.cfg)
        accepted = bool(dialog.exec())
        result = dialog.result_launcher
        # Duplicate saves as it goes, so a cancel after it still changed the lists.
        if not (accepted and result) and not dialog.saved_ids:
            return
        if accepted and result:
            # After Duplicate the result is the copy, already saved. Adding replaces it.
            ctl.cfg.add_launcher(result)
        fill_main_dropdown(ctl.dropdown, ctl.cfg)
        ctl._refresh_open_container()
        ctl._sync_groups_after_change()

    def on_edit_launcher(self, launcher: Launcher) -> None:
        self._ctl.show_add_dialog(launcher)
        if self._ctl.settings.pinned_open:
            self._ctl._apply_pinned_state()

    def on_delete_launcher(self, launcher: Launcher) -> None:
        if not self._ctl._confirm_delete("Delete Launcher", launcher.name):
            return
        self._ctl.cfg.remove_launcher(launcher.id)
        self._ctl._refresh_open_list()

    def show_manager_dialog(self) -> None:
        from .controller import fill_main_dropdown

        ctl = self._ctl
        ManagerDialog(ctl.cfg, ctl.trigger).exec()
        # Launchers may have changed. Rebuild, then restore the pin state.
        fill_main_dropdown(ctl.dropdown, ctl.cfg)
        ctl._refresh_open_container()
        ctl._sync_groups_after_change()
        ctl._apply_pinned_state()

    def show_group_dialog(self, existing: Group | None = None, *, scheduled: bool = False) -> None:
        ctl = self._ctl
        dialog = GroupDialog(ctl.cfg, existing, ctl.trigger, scheduled=scheduled)
        dialog.launchers_changed.connect(ctl._refresh_open_list)
        accepted = bool(dialog.exec())
        result = dialog.result_group
        if accepted and result is not None:
            if existing is None:
                ctl.cfg.add_group(result)
            else:
                ctl.cfg.update_group(result)
        ctl._refresh_open_list()
        ctl._sync_groups_after_change()

    def show_group_manager(self) -> None:
        ctl = self._ctl
        GroupManagerDialog(ctl.cfg, ctl.trigger).exec()
        ctl._refresh_open_list()
        ctl._sync_groups_after_change()

    def show_schedule_manager(self) -> None:
        ctl = self._ctl
        ScheduleManagerDialog(ctl.cfg, ctl.trigger).exec()
        ctl._refresh_open_list()
        ctl._sync_groups_after_change()

    def on_group_edit(self, row: Launcher) -> None:
        group = self._ctl._group_by_id(row.id)
        if group is not None:
            self._ctl.show_group_dialog(group)

    def on_group_delete(self, row: Launcher) -> None:
        ctl = self._ctl
        group = ctl._group_by_id(row.id)
        title = "Delete Schedule" if group is not None and group.scheduled else "Delete Execute Group"
        if group is None or not ctl._confirm_delete(title, group.name):
            return
        ctl.cfg.remove_group(group.id)
        ctl._sync_groups_after_change()

    def show_container_dialog(self, existing: ContainerGroup | None = None) -> None:
        ctl = self._ctl
        dialog = ContainerDialog(ctl.cfg, existing, ctl.trigger)
        dialog.launchers_changed.connect(ctl._refresh_open_list)
        accepted = bool(dialog.exec())
        result = dialog.result_group
        if accepted and result is not None:
            if existing is None:
                ctl.cfg.add_container_group(result)
            else:
                ctl.cfg.update_container_group(result)
        ctl._refresh_open_list()

    def show_container_manager(self) -> None:
        ctl = self._ctl
        ContainerManagerDialog(ctl.cfg, ctl.trigger).exec()
        ctl._refresh_open_list()

    def on_container_edit(self, group_id: str) -> None:
        group = self._ctl._container_by_id(group_id)
        if group is not None:
            self._ctl.show_container_dialog(group)

    def on_container_delete(self, group_id: str) -> None:
        ctl = self._ctl
        group = ctl._container_by_id(group_id)
        if group is None or not ctl._confirm_delete("Delete Container Group", group.name):
            return
        ctl.cfg.remove_container_group(group.id)
        ctl.container_menu.hide()
        ctl._refresh_open_list()

    def show_help(self) -> None:
        """The Help window, from the arrow menu. One at a time; a second Help brings it forward."""
        if self.help_window is None:
            self.help_window = HelpWindow(self._ctl.trigger)
        self.help_window.show()
        self.help_window.raise_()
        self.help_window.activateWindow()

    def apply_theme(self) -> None:
        if self.help_window is not None:
            self.help_window.apply_theme()

    def report_load_problems(self) -> None:
        ctl = self._ctl
        problems = ctl.cfg.load_problems
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
        ctl.cfg.load_problems = []
        stay_on_top_warning(ctl.trigger, "Config problems", text)
