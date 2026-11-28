"""Add or edit a container group.

A container group is a submenu. The shared row behaviour (click to include,
drag to reorder) is in member_dialog. This screen adds an Only in Container
Group switch per row. It is the opposite of Include in dropdown list.
Changing it updates that switch and every group.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer

from ..config import ContainerGroup, ContainerMember, Launcher
from .member_dialog import MemberPickerDialog, _ClickCell
from .stay_on_top import warning
from .toggle_switch import ToggleSwitch

ONLY_TIP = "Keep this launcher out of the main list. Tick it in the list first."

_NOTE = (
    "These items open in a submenu when you hover this container group. "
    "They are not run together."
)


class _SwitchCell(_ClickCell):
    """A row cell whose whole area toggles Only in Container Group."""


class ContainerDialog(MemberPickerDialog):
    """Name a container group and choose which launchers appear in its submenu."""

    NOUN = "Container Group"
    NOTE = _NOTE
    COLUMNS = ("Launcher", "Only in Container Group")
    COLUMN_TIPS = (
        MemberPickerDialog.COLUMN_TIPS[0],
        ONLY_TIP,
    )
    SIZE = (760, 480)
    ROW_HEIGHT = 36
    DRAG_ROLES = ("member", "only")

    def _saved_groups(self) -> list[ContainerGroup]:
        return self._cfg.config.container_groups

    def only_switch(self, launcher_id: str) -> _SwitchCell:
        return self._cell(launcher_id, "only")  # type: ignore[return-value]

    @staticmethod
    def _hidden_from_main(launcher: Launcher | None) -> bool:
        return launcher is not None and not launcher.show_in_main

    def _fill_row(self, row: int, launcher: Launcher, member: bool) -> None:
        # The column heading names the switch, so the switch has no label.
        switch = ToggleSwitch()
        switch.setProperty("launcher_id", launcher.id)
        switch.setProperty("role", "only")
        switch.setChecked(self._hidden_from_main(launcher))
        switch.setEnabled(member)
        cell = _SwitchCell(switch, on_click=lambda lid=launcher.id: self._on_only_clicked(lid))
        cell.setToolTip(ONLY_TIP)
        self._paint(cell, member)
        self._table.setCellWidget(row, 1, cell)

    def _on_only_clicked(self, launcher_id: str) -> None:
        if launcher_id not in self._selected:
            return
        launcher = self._launcher(launcher_id)
        if launcher is None:
            return
        self._cfg.set_shown_in_main_menu(launcher_id, not launcher.show_in_main)
        self.launchers_changed.emit()
        QTimer.singleShot(0, self._rebuild)

    def _apply(self) -> bool:
        name = self._name_edit.text().strip()
        if not name:
            warning(self, "Missing info", "Name is required.")
            return False
        members = [ContainerMember(launcher_id) for launcher_id in self._selected]
        if self._original is not None:
            self._original.name = name
            self._original.members = members
            self._result = self._original
        else:
            self._result = ContainerGroup.new(name, members)
        return True

    def _store(self, group) -> None:
        self._cfg.add_container_group(group)

    def _copy_saved(self, group_id: str):
        return self._cfg.duplicate_container_group(group_id)
