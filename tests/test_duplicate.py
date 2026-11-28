"""Duplicate on the launcher, execute group, schedule and container group screens."""

from datetime import datetime

from PySide6.QtWidgets import QApplication

from runner.config import (
    ConfigManager,
    ContainerGroup,
    ContainerMember,
    Group,
    GroupMember,
    Launcher,
    ScheduleEntry,
    duplicate_name,
)
from runner.ui.add_dialog import AddEditDialog
from runner.ui.container_dialog import ContainerDialog
from runner.ui.group_dialog import GroupDialog
from runner.ui.schedule_pickers import DatePickerDialog


def _cfg() -> ConfigManager:
    cfg = ConfigManager()
    cfg.config.launchers = []
    cfg.config.groups = []
    cfg.config.container_groups = []
    cfg.config.main_order = []
    return cfg


def test_copy_names_count_on_from_the_base_name():
    assert duplicate_name("Brave", ["Brave"]) == "Brave (1)"
    assert duplicate_name("Brave", ["Brave", "Brave (1)"]) == "Brave (2)"
    assert duplicate_name("Brave (1)", ["Brave", "Brave (1)", "Brave (4)"]) == "Brave (5)"
    # Another name that only starts the same is not counted.
    assert duplicate_name("Brave", ["Brave", "Brave Beta (7)"]) == "Brave (1)"


def test_duplicating_a_launcher_copies_it_into_every_list_beside_the_original():
    cfg = _cfg()
    alpha = Launcher.new("Alpha", "alpha", args="--x", working_dir="/tmp", show_in_main=False, source="tool")
    beta = Launcher.new("Beta", "beta")
    cfg.config.launchers = [alpha, beta]
    cfg.config.groups = [Group("g", "G", [GroupMember(alpha.id, concurrent=True), GroupMember(beta.id)])]
    cfg.config.container_groups = [ContainerGroup("c", "C", [ContainerMember(alpha.id), ContainerMember(beta.id)])]
    cfg.config.main_order = [f"launcher:{beta.id}", f"launcher:{alpha.id}"]

    copy = cfg.duplicate_launcher(alpha.id)

    assert copy is not None and copy.id != alpha.id
    assert (copy.name, copy.command, copy.args, copy.working_dir, copy.show_in_main) == (
        "Alpha (1)", "alpha", "--x", "/tmp", False,
    )
    assert copy.source is None  # made in Runner, so Runner may change it
    assert [item.id for item in cfg.config.launchers] == [alpha.id, copy.id, beta.id]
    members = cfg.config.groups[0].members
    assert [(m.launcher_id, m.concurrent) for m in members] == [
        (alpha.id, True), (copy.id, True), (beta.id, False),
    ]
    assert [m.launcher_id for m in cfg.config.container_groups[0].members] == [alpha.id, copy.id, beta.id]
    assert cfg.config.main_order == [f"launcher:{beta.id}", f"launcher:{alpha.id}", f"launcher:{copy.id}"]


def test_the_launcher_screen_saves_then_edits_the_copy(qapp, qtbot):
    cfg = _cfg()
    alpha = Launcher.new("Alpha", "alpha")
    cfg.config.launchers = [alpha]
    cfg.config.groups = [Group("g", "G", [GroupMember(alpha.id)])]
    dialog = AddEditDialog(alpha, cfg=cfg)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog._command_edit.setText("alpha --changed")

    dialog.duplicate_button.click()

    # The edit to the original was saved first.
    assert alpha.command == "alpha --changed"
    copy = cfg.config.launchers[1]
    assert copy.name == "Alpha (1)" and copy.command == "alpha --changed"
    assert dialog.saved_ids == [alpha.id]
    assert dialog.windowTitle() == "Edit Launcher"
    assert dialog._name_edit.text() == "Alpha (1)"
    assert dialog._name_edit.selectedText() == "Alpha (1)"
    qtbot.waitUntil(lambda: QApplication.focusWidget() is dialog._name_edit)
    assert [m.launcher_id for m in cfg.config.groups[0].members] == [alpha.id, copy.id]

    # Saving now edits the copy, not the original, and adding it again does not list it twice.
    dialog._name_edit.setText("Alpha work")
    dialog.accept()
    cfg.add_launcher(dialog.result_launcher)
    assert [item.name for item in cfg.config.launchers] == ["Alpha", "Alpha work"]


def test_duplicate_on_a_new_launcher_saves_both(qapp, qtbot):
    cfg = _cfg()
    dialog = AddEditDialog(None, cfg=cfg)
    qtbot.addWidget(dialog)
    dialog._name_edit.setText("Notes")
    dialog._command_edit.setText("notes")
    dialog.duplicate_button.click()
    dialog.duplicate_button.click()
    assert [item.name for item in cfg.config.launchers] == ["Notes", "Notes (1)", "Notes (2)"]
    assert dialog.result_launcher is cfg.config.launchers[2]


def test_duplicate_needs_the_required_fields(qapp, qtbot, monkeypatch):
    cfg = _cfg()
    warned = []
    monkeypatch.setattr("runner.ui.add_dialog.warning", lambda *args: warned.append(args))
    dialog = AddEditDialog(None, cfg=cfg)
    qtbot.addWidget(dialog)
    dialog.duplicate_button.click()
    assert warned and cfg.config.launchers == []


def test_the_launcher_screen_has_no_duplicate_without_a_config(qapp, qtbot):
    dialog = AddEditDialog(None)
    qtbot.addWidget(dialog)
    dialog.show()
    assert not dialog.duplicate_button.isVisible()


def test_duplicating_a_schedule_copies_its_dates_with_new_ids(qapp, qtbot):
    cfg = _cfg()
    alpha = Launcher.new("Alpha", "alpha")
    cfg.config.launchers = [alpha]
    entry = ScheduleEntry.new(datetime(2027, 1, 5, 9, 0))
    entry.weeks = 1
    group = Group("s", "Backup", [GroupMember(alpha.id, concurrent=True)], show_contents=True,
                  scheduled=True, schedule=[entry], click_runs=True)
    cfg.config.groups = [group, Group("other", "Other")]
    dialog = GroupDialog(cfg, group)
    qtbot.addWidget(dialog)

    dialog.duplicate_button.click()

    copy = cfg.config.groups[1]
    assert [g.name for g in cfg.config.groups] == ["Backup", "Backup (1)", "Other"]
    assert (copy.scheduled, copy.click_runs, copy.show_contents) == (True, True, True)
    assert [(m.launcher_id, m.concurrent) for m in copy.members] == [(alpha.id, True)]
    assert copy.members[0] is not group.members[0]
    assert copy.schedule[0].id != entry.id and copy.schedule[0].weeks == 1
    assert dialog.windowTitle() == "Edit Execute Group"
    assert dialog.schedule_editor.ordered_ids() == [copy.schedule[0].id]

    dialog._name_edit.setText("Backup weekly")
    dialog.accept()
    assert dialog.result_group is copy
    assert copy.name == "Backup weekly" and copy.schedule[0].id != entry.id
    assert group.name == "Backup"


def test_duplicating_a_container_group(qapp, qtbot):
    cfg = _cfg()
    alpha = Launcher.new("Alpha", "alpha")
    cfg.config.launchers = [alpha]
    dialog = ContainerDialog(cfg, None)
    qtbot.addWidget(dialog)
    dialog._name_edit.setText("Tools")
    dialog.name_cell(alpha.id).box.setChecked(True)
    dialog.duplicate_button.click()
    names = [(g.name, [m.launcher_id for m in g.members]) for g in cfg.config.container_groups]
    assert names == [("Tools", [alpha.id]), ("Tools (1)", [alpha.id])]
    assert dialog.windowTitle() == "Edit Container Group"
    assert dialog.saved_ids == [cfg.config.container_groups[0].id]


def test_the_dial_settings_live_in_the_three_line_menu(qapp, qtbot):
    dialog = DatePickerDialog(datetime(2026, 11, 24, 9, 0), show_minutes=False)
    qtbot.addWidget(dialog)
    assert dialog.menu_button.menu() is dialog.menu
    labels = [action.text() for action in dialog.menu.actions() if not action.isSeparator()]
    assert labels == ["Show minutes", "Now"]
    assert dialog.minutes_action.isCheckable() and not dialog.minutes_action.isChecked()


# ------------------------------------------------- right-click Duplicate


def _controller(qapp, monkeypatch, tmp_path):
    """The real controller over a throwaway config: two launchers, a group, a schedule, a container."""
    from unittest.mock import MagicMock

    from runner.controller import RunnerController

    monkeypatch.setattr("runner.config.platformdirs.user_config_dir", lambda *a, **k: str(tmp_path))
    cfg = ConfigManager()
    alpha, beta = Launcher.new("Alpha", "a"), Launcher.new("Beta", "b")
    cfg.config.launchers = [alpha, beta]
    cfg.config.groups = [
        Group.new("Class", [GroupMember(alpha.id)]),
        Group("sched", "Nightly", [GroupMember(beta.id)], scheduled=True,
              schedule=[ScheduleEntry.new(datetime(2030, 1, 1, 2, 0))]),
    ]
    cfg.config.container_groups = [ContainerGroup.new("Projects", [ContainerMember(alpha.id)])]
    monkeypatch.setattr("runner.controller.create_tray", lambda **_: MagicMock())
    ctl = RunnerController(qapp, cfg)
    ctl.greeting.dismiss_for_session()
    return ctl


def _record_and_cancel(monkeypatch, dialog_cls, seen: list):
    """Stand in for the modal exec: note what the screen shows, then press Cancel."""

    def fake_exec(self):
        seen.append((self.windowTitle(), self._name_edit.text(), self._name_edit.selectedText()))
        return 0

    monkeypatch.setattr(dialog_cls, "exec", fake_exec)


def test_right_click_duplicate_on_a_launcher_opens_the_saved_copy(qapp, qtbot, monkeypatch, tmp_path):
    ctl = _controller(qapp, monkeypatch, tmp_path)
    seen = []
    _record_and_cancel(monkeypatch, AddEditDialog, seen)
    alpha = ctl.cfg.config.launchers[0]

    ctl.dropdown.duplicate_requested.emit(alpha)

    assert seen == [("Edit Launcher", "Alpha (1)", "Alpha (1)")]
    # Cancel on the copy's screen keeps the copy; it is beside the original everywhere.
    names = [item.name for item in ctl.cfg.config.launchers]
    assert names == ["Alpha", "Alpha (1)", "Beta"]
    copy = ctl.cfg.config.launchers[1]
    assert [m.launcher_id for m in ctl.cfg.config.groups[0].members] == [alpha.id, copy.id]
    shown = [b.launcher.name for b in ctl.dropdown._buttons if hasattr(b, "launcher")]
    assert "Alpha (1)" in shown


def test_right_click_duplicate_on_a_group_and_a_schedule(qapp, qtbot, monkeypatch, tmp_path):
    ctl = _controller(qapp, monkeypatch, tmp_path)
    seen = []
    _record_and_cancel(monkeypatch, GroupDialog, seen)
    group, schedule = ctl.cfg.config.groups
    row = Launcher(id=group.id, name=group.name, command="")

    ctl.group_panel.duplicate_requested.emit(row)
    ctl.schedule_list.duplicate_requested.emit(Launcher(id=schedule.id, name=schedule.name, command=""))

    assert seen == [
        ("Edit Execute Group", "Class (1)", "Class (1)"),
        ("Edit Execute Group", "Nightly (1)", "Nightly (1)"),
    ]
    assert [g.name for g in ctl.cfg.config.groups] == ["Class", "Class (1)", "Nightly", "Nightly (1)"]
    assert ctl.cfg.config.groups[3].scheduled is True


def test_right_click_duplicate_on_a_container(qapp, qtbot, monkeypatch, tmp_path):
    ctl = _controller(qapp, monkeypatch, tmp_path)
    seen = []
    _record_and_cancel(monkeypatch, ContainerDialog, seen)
    original = ctl.cfg.config.container_groups[0]

    ctl.dropdown.submenu_duplicate_requested.emit(original.id)

    assert seen == [("Edit Container Group", "Projects (1)", "Projects (1)")]
    assert [g.name for g in ctl.cfg.config.container_groups] == ["Projects", "Projects (1)"]
    assert [name for _gid, name in ctl.dropdown._submenu_items] == ["Projects", "Projects (1)"]
