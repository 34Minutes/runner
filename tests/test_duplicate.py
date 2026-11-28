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
