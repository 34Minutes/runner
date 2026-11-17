"""Add or edit an execute group.

The shared row behaviour (click to include, drag to reorder) is in
member_dialog. This screen adds two checkboxes per row. Concurrent starts the
launcher together with its neighbours. Only In Groups is the opposite of
Include in dropdown list; changing it updates that switch and every container
group. Show group contents is off until the user turns it on. Only then does
hovering that group open its launchers.
"""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QWidget

from ..config import Group, GroupMember, Launcher
from ..containers import shown_in_main_menu
from .member_dialog import MemberPickerDialog, _ClickCell, _DragGhost, _NameCell  # noqa: F401
from .stay_on_top import warning
from .toggle_switch import ToggleSwitch

_NOTE = "These items will be executed in the order it appears in the list below"
# Kept for callers and tests that read the original colours from here.
_DRAG_BORDER = "#ffd600"
_SELECTED_BG = "#3c3c3c"
_SELECTED_FG = "#f2f2f2"


class GroupDialog(MemberPickerDialog):
    """Name a group and choose which launchers it runs, and in what order."""

    NOUN = "Execute Group"
    NOTE = _NOTE
    COLUMNS = ("Launcher", "Concurrent", "Only In Groups")
    SIZE = (680, 480)
    ROW_HEIGHT = 34
    DRAG_ROLES = ("member", "concurrent", "only")

    def _init_state(self) -> None:
        self._concurrent: dict[str, bool] = {}

    def _load_members(self, members: list[GroupMember]) -> None:
        self._concurrent = {member.launcher_id: member.concurrent for member in members}

    def _extra_widgets(self, group: Group | None) -> list[QWidget]:
        self._show_contents = ToggleSwitch("Show group contents")
        self._show_contents.setChecked(group is not None and group.show_contents)
        return [self._show_contents]

    def _saved_groups(self) -> list[Group]:
        return self._cfg.config.groups

    def concurrent_checkbox(self, launcher_id: str) -> _ClickCell:
        return self._cell(launcher_id, "concurrent")

    def only_in_groups_checkbox(self, launcher_id: str) -> _ClickCell:
        return self._cell(launcher_id, "only")

    def _fill_row(self, row: int, launcher: Launcher, member: bool) -> None:
        self._table.setCellWidget(row, 1, self._check_widget(
            launcher.id,
            "concurrent",
            self._concurrent.get(launcher.id, False),
            member,
        ))
        self._table.setCellWidget(row, 2, self._check_widget(
            launcher.id,
            "only",
            not shown_in_main_menu(launcher, self._cfg.config.container_groups),
            member,
        ))

    def _check_widget(self, launcher_id: str, role: str, checked: bool, member: bool) -> _ClickCell:
        box = QCheckBox()
        box.setProperty("launcher_id", launcher_id)
        box.setProperty("role", role)
        box.setChecked(checked)
        cell = _ClickCell(box, on_click=lambda b=box: b.toggle())
        if role == "concurrent":
            box.toggled.connect(lambda state, lid=launcher_id: self._on_concurrent_toggled(lid, state))
        else:
            box.toggled.connect(lambda state, lid=launcher_id: self._set_only_in_groups(lid, state))
        self._paint(cell, member)
        return cell

    def _on_concurrent_toggled(self, launcher_id: str, checked: bool) -> None:
        self._concurrent[launcher_id] = checked

    def _on_unselected(self, launcher_id: str) -> None:
        self._concurrent[launcher_id] = False

    def _absorb_member(self, member: GroupMember) -> None:
        self._concurrent[member.launcher_id] = member.concurrent

    def _set_only_in_groups(self, launcher_id: str, checked: bool) -> None:
        self._cfg.set_shown_in_main_menu(launcher_id, not checked)
        self.launchers_changed.emit()

    def accept(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            warning(self, "Missing info", "Name is required.")
            return
        members = [
            GroupMember(launcher_id, concurrent=self._concurrent.get(launcher_id, False))
            for launcher_id in self._selected
        ]
        show_contents = self._show_contents.isChecked()
        if self._original is not None:
            self._original.name = name
            self._original.members = members
            self._original.show_contents = show_contents
            self._result = self._original
        else:
            created = Group.new(name, members)
            created.show_contents = show_contents
            self._result = created
        super().accept()
