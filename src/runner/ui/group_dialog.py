"""Add or edit an execute group.

The shared row behaviour (click to include, drag to reorder) is in
member_dialog. This screen adds two checkboxes per row. Concurrent starts the
launcher together with its neighbours. Only In Groups is the opposite of
Include in dropdown list; changing it updates that switch and every container
group. Show group contents is off until the user turns it on. Only then does
hovering that group open its launchers.

The Schedule switch turns the group into a schedule: it runs on the dates in
the schedule area below the table instead of from the Execute Groups list,
and shows only in the Schedules list. Turned off, it is an execute group
again and its dates are kept, greyed out.
"""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QWidget

from ..config import ConfigManager, Group, GroupMember, Launcher
from . import theme
from .member_dialog import MemberPickerDialog, _ClickCell
from .schedule_editor import ScheduleEditor
from .stay_on_top import warning
from .toggle_switch import ToggleSwitch

SCHEDULE_NOTE = "Scheduled items will not appear in the launcher menu."

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
    SIZE = (720, 700)
    ROW_HEIGHT = 34
    DRAG_ROLES = ("member", "concurrent", "only")

    def __init__(
        self,
        cfg: ConfigManager,
        group: Group | None = None,
        parent: QWidget | None = None,
        *,
        scheduled: bool = False,
    ) -> None:
        # Read by _extra_widgets, which the base class calls while it builds.
        self._start_scheduled = scheduled if group is None else group.scheduled
        super().__init__(cfg, group, parent)
        if group is None and scheduled:
            self.setWindowTitle("Add Schedule")

    def _init_state(self) -> None:
        self._concurrent: dict[str, bool] = {}

    def _load_members(self, members: list[GroupMember]) -> None:
        self._concurrent = {member.launcher_id: member.concurrent for member in members}

    def _extra_widgets(self, group: Group | None) -> list[QWidget]:
        self._show_contents = ToggleSwitch("Show group contents")
        self._show_contents.setChecked(group is not None and group.show_contents)
        self.schedule_switch = ToggleSwitch("Schedule")
        self.schedule_switch.setChecked(self._start_scheduled)
        self.schedule_switch.toggled.connect(self._on_schedule_toggled)
        note = QLabel(SCHEDULE_NOTE)
        note.setStyleSheet(f"color: {theme.current().hint_fg};")
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(self._show_contents)
        line.addSpacing(24)
        line.addWidget(self.schedule_switch)
        line.addSpacing(10)
        line.addWidget(note, 1)
        return [row]

    def _bottom_widgets(self, group: Group | None) -> list[QWidget]:
        self.schedule_editor = ScheduleEditor(group.schedule if group is not None else [], self)
        self.schedule_editor.set_active(self._start_scheduled)
        return [self.schedule_editor]

    def _on_schedule_toggled(self, checked: bool) -> None:
        editor = getattr(self, "schedule_editor", None)
        if editor is not None:
            editor.set_active(checked)

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
            not launcher.show_in_main,
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
        scheduled = self.schedule_switch.isChecked()
        schedule = self.schedule_editor.entries()
        if self._original is not None:
            self._original.name = name
            self._original.members = members
            self._original.show_contents = show_contents
            self._original.scheduled = scheduled
            self._original.schedule = schedule
            self._result = self._original
        else:
            created = Group.new(name, members)
            created.show_contents = show_contents
            created.scheduled = scheduled
            created.schedule = schedule
            self._result = created
        super().accept()
