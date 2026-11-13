"""Container groups: a submenu of launchers, not a run list."""

from unittest.mock import patch

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QContextMenuEvent, QEnterEvent
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from runner.config import (
    AppConfig,
    ConfigManager,
    ContainerGroup,
    ContainerMember,
    Group,
    GroupMember,
    Launcher,
)
from runner.containers import shown_in_main_menu, submenu_launchers
from runner.ui.add_dialog import AddEditDialog
from runner.ui.container_dialog import ContainerDialog, _NOTE
from runner.ui.container_manager import ContainerManagerDialog
from runner.ui.dropdown import DropdownPanel, SubmenuButton
from runner.ui.group_dialog import GroupDialog, _SELECTED_BG
from runner.ui.launch_button import LaunchButton
from runner.ui.trigger import TriggerWidget


def _isolate_config(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "runner.config.platformdirs.user_config_dir",
        lambda *a, **k: str(tmp_path),
    )
    return ConfigManager()


def test_main_list_hides_a_launcher_when_any_container_switch_is_on():
    alpha = Launcher.new("Alpha", "alpha")
    beta = Launcher.new("Beta", "beta")
    reserved = Launcher.new("Reserved", "reserved", only_in_groups=True)
    disabled = Launcher.new("Off", "off", enabled=False)
    quiet = ContainerGroup.new(
        "Quiet",
        [ContainerMember(alpha.id, only_in_container=False), ContainerMember(beta.id)],
    )
    loud = ContainerGroup.new(
        "Loud",
        [ContainerMember(alpha.id, only_in_container=False)],
    )
    assert shown_in_main_menu(alpha, [quiet, loud]) is True
    assert shown_in_main_menu(beta, [quiet, loud]) is True
    assert shown_in_main_menu(reserved, [quiet]) is False
    assert shown_in_main_menu(disabled, []) is False

    loud.members[0].only_in_container = True
    assert shown_in_main_menu(alpha, [quiet, loud]) is False
    assert shown_in_main_menu(beta, [quiet, loud]) is True

    # A launcher in no container group stays on the main list.
    alone = Launcher.new("Alone", "alone")
    assert shown_in_main_menu(alone, [quiet, loud]) is True


def test_submenu_lists_enabled_members_in_container_order():
    first = Launcher.new("First", "first", only_in_groups=True)
    second = Launcher.new("Second", "second")
    disabled = Launcher.new("Off", "off", enabled=False)
    group = ContainerGroup.new(
        "Apps",
        [
            ContainerMember(second.id),
            ContainerMember("missing"),
            ContainerMember(disabled.id, only_in_container=True),
            ContainerMember(first.id, only_in_container=True),
        ],
    )
    assert [item.name for item in submenu_launchers(group, [first, second, disabled])] == [
        "Second",
        "First",
    ]


def test_container_groups_roundtrip_and_follow_a_deleted_launcher(tmp_path, monkeypatch):
    mgr = _isolate_config(monkeypatch, tmp_path)
    alpha = Launcher.new("Alpha", "a")
    beta = Launcher.new("Beta", "b")
    mgr.add_launcher(alpha)
    mgr.add_launcher(beta)
    mgr.add_container_group(
        ContainerGroup.new(
            "Folder",
            [
                ContainerMember(alpha.id, only_in_container=True),
                ContainerMember(beta.id),
            ],
        )
    )
    mgr.add_group(Group.new("Run", [GroupMember(alpha.id, concurrent=True)]))

    loaded = ConfigManager()
    assert loaded.config.version == 1
    assert loaded.config.container_groups[0].name == "Folder"
    assert loaded.config.container_groups[0].members[0].only_in_container is True
    assert [item.name for item in loaded.get_main_view_launchers()] == ["Beta"]

    # An old file with no container groups still loads, and those launchers stay visible.
    restored = AppConfig.from_dict({"version": 1, "launchers": [{"id": beta.id, "name": "Beta", "command": "b"}]})
    assert restored.container_groups == []
    assert shown_in_main_menu(restored.launchers[0], restored.container_groups) is True

    loaded.remove_launcher(alpha.id)
    assert loaded.config.container_groups[0].members == [ContainerMember(beta.id)]
    assert loaded.config.groups[0].members == []


def test_membership_edit_keeps_flags_and_order(tmp_path, monkeypatch):
    mgr = _isolate_config(monkeypatch, tmp_path)
    alpha = Launcher.new("Alpha", "a")
    beta = Launcher.new("Beta", "b")
    mgr.add_launcher(alpha)
    mgr.add_launcher(beta)
    run = Group.new(
        "Run",
        [GroupMember(beta.id), GroupMember(alpha.id, concurrent=True)],
    )
    mgr.add_group(run)
    later = Group.new("Later")
    mgr.add_group(later)
    folder = ContainerGroup.new(
        "Folder",
        [ContainerMember(beta.id), ContainerMember(alpha.id, only_in_container=True)],
    )
    mgr.add_container_group(folder)

    mgr.set_launcher_membership(alpha.id, [folder.id], [run.id, later.id])
    run_members = mgr.config.groups[0].members
    assert [member.launcher_id for member in run_members] == [beta.id, alpha.id]
    assert run_members[1].concurrent is True
    assert [member.launcher_id for member in mgr.config.groups[1].members] == [alpha.id]
    assert mgr.config.groups[1].members[0].concurrent is False
    folder_members = mgr.config.container_groups[0].members
    assert [member.launcher_id for member in folder_members] == [beta.id, alpha.id]
    assert folder_members[1].only_in_container is True

    mgr.set_launcher_membership(alpha.id, [], [later.id])
    assert mgr.config.container_groups[0].members == [ContainerMember(beta.id)]
    assert [member.launcher_id for member in mgr.config.groups[0].members] == [beta.id]
    assert [member.launcher_id for member in mgr.config.groups[1].members] == [alpha.id]


def test_container_dialog_saves_click_order_and_the_switch(qapp, qtbot, tmp_path, monkeypatch):
    mgr = _isolate_config(monkeypatch, tmp_path)
    alpha = Launcher.new("Alpha", "a", only_in_groups=True)
    beta = Launcher.new("Beta", "b")
    mgr.add_launcher(alpha)
    mgr.add_launcher(beta)

    dialog = ContainerDialog(mgr, None)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    assert dialog.windowTitle() == "Add Container Group"
    headers = [dialog._table.horizontalHeaderItem(column).text() for column in range(2)]
    assert headers == ["Launcher", "Only in Container Group"]
    notes = [label.text() for label in dialog.findChildren(QLabel)]
    assert _NOTE in notes
    # Hidden from the main list, still offered here.
    assert dialog.display_ids() == [alpha.id, beta.id]

    def click_name(launcher_id):
        qtbot.mouseClick(dialog.name_cell(launcher_id), Qt.MouseButton.LeftButton)
        qapp.processEvents()

    click_name(beta.id)
    click_name(alpha.id)
    assert dialog.display_ids() == [beta.id, alpha.id, ]
    assert _SELECTED_BG in dialog.name_cell(beta.id).styleSheet()
    assert dialog.only_switch(alpha.id).box.text() == "Only in Container Group"
    assert dialog.only_switch(alpha.id).box.isChecked() is False

    qtbot.mouseClick(dialog.only_switch(alpha.id), Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert dialog.only_switch(alpha.id).box.isChecked() is True

    click_name(alpha.id)
    assert dialog.only_switch(alpha.id).box.isChecked() is False
    click_name(alpha.id)
    qtbot.mouseClick(dialog.only_switch(alpha.id), Qt.MouseButton.LeftButton)
    qapp.processEvents()

    dialog._name_edit.setText("  ")
    with patch("runner.ui.container_dialog.warning") as warn:
        dialog.accept()
    assert warn.called
    assert dialog.result_group is None

    dialog._name_edit.setText("Folder")
    dialog.accept()
    result = dialog.result_group
    assert result is not None
    assert result.name == "Folder"
    assert [(member.launcher_id, member.only_in_container) for member in result.members] == [
        (beta.id, False),
        (alpha.id, True),
    ]


def test_container_and_execute_dialogs_list_launchers_hidden_from_the_main_popup(
    qapp, qtbot, tmp_path, monkeypatch
):
    mgr = _isolate_config(monkeypatch, tmp_path)
    hidden = Launcher.new("Hidden", "hidden")
    mgr.add_launcher(hidden)
    mgr.add_container_group(
        ContainerGroup.new("Folder", [ContainerMember(hidden.id, only_in_container=True)])
    )
    assert mgr.get_main_view_launchers() == []

    container = ContainerDialog(mgr, None)
    execute = GroupDialog(mgr, None)
    qtbot.addWidget(container)
    qtbot.addWidget(execute)
    assert container.display_ids() == [hidden.id]
    assert execute.display_ids() == [hidden.id]
    container.close()
    execute.close()


def test_launcher_screen_adds_and_removes_both_kinds_of_group(qapp, qtbot, tmp_path, monkeypatch):
    mgr = _isolate_config(monkeypatch, tmp_path)
    alpha = Launcher.new("Alpha", "a")
    mgr.add_launcher(alpha)
    run = Group.new("Run", [GroupMember(alpha.id, concurrent=True)])
    later = Group.new("Later")
    mgr.add_group(run)
    mgr.add_group(later)
    folder = ContainerGroup.new("Folder", [ContainerMember(alpha.id, only_in_container=True)])
    extra = ContainerGroup.new("Extra")
    mgr.add_container_group(folder)
    mgr.add_container_group(extra)

    dialog = AddEditDialog(alpha, cfg=mgr)
    qtbot.addWidget(dialog)
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert "Container groups I belong to" in labels
    assert "Execute groups I belong to" in labels
    assert dialog._container_membership.selected_ids() == [folder.id]
    assert dialog._execute_membership.selected_ids() == [run.id]

    dialog._container_membership._on_add()
    assert dialog._container_membership.selected_ids() == [folder.id, extra.id]
    dialog._execute_membership._on_add()
    assert dialog._execute_membership.selected_ids() == [run.id, later.id]

    dialog._container_membership._list.setCurrentRow(0)
    dialog._container_membership._on_remove()
    assert dialog._container_membership.selected_ids() == [extra.id]

    dialog.accept()
    assert [member.launcher_id for member in mgr.config.container_groups[0].members] == []
    assert mgr.config.container_groups[1].members == [ContainerMember(alpha.id)]
    assert mgr.config.groups[0].members == [GroupMember(alpha.id, concurrent=True)]
    assert mgr.config.groups[1].members == [GroupMember(alpha.id)]


def test_manage_container_groups_deletes_the_group_and_keeps_its_launchers(
    qapp, qtbot, tmp_path, monkeypatch
):
    mgr = _isolate_config(monkeypatch, tmp_path)
    launcher = Launcher.new("Alpha", "a")
    mgr.add_launcher(launcher)
    mgr.add_container_group(ContainerGroup.new("Folder", [ContainerMember(launcher.id)]))

    dialog = ContainerManagerDialog(mgr)
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Manage Container Groups"
    assert dialog._list.item(0).text() == "Folder  (1 launcher)"
    dialog._list.setCurrentRow(0)
    with patch("runner.ui.container_manager.question", return_value=QMessageBox.StandardButton.Yes):
        dialog._on_delete()
    assert dialog._list.count() == 0
    assert [item.name for item in mgr.config.launchers] == ["Alpha"]
    assert mgr.config.container_groups == []


def test_arrow_menu_adds_container_group_after_execute_groups(qapp, qtbot):
    trigger = TriggerWidget(AppConfig())
    qtbot.addWidget(trigger)
    seen = []
    trigger.request_add_container.connect(lambda: seen.append("add"))
    trigger.request_manage_containers.connect(lambda: seen.append("manage"))
    trigger._show_context_menu(QPoint(8, 8))
    trigger._action_add_container.trigger()
    trigger._action_manage_containers.trigger()
    assert seen == ["add", "manage"]


def test_main_popup_shows_container_rows_and_a_click_does_not_launch(qapp, qtbot):
    cfg = AppConfig()
    alpha = Launcher.new("Alpha", "a")
    beta = Launcher.new("Beta", "b")
    cfg.launchers = [alpha, beta]
    panel = DropdownPanel(cfg)
    qtbot.addWidget(panel)
    panel.set_submenu_items([("folder", "Folder")])
    panel.rebuild_buttons([alpha, beta])
    panel.show()
    qtbot.waitExposed(panel)

    assert [type(button).__name__ for button in panel._buttons] == [
        "SubmenuButton",
        "LaunchButton",
        "LaunchButton",
    ]
    folder = panel.submenu_button("folder")
    assert isinstance(folder, SubmenuButton)
    assert folder.text().endswith("›")

    launched = []
    hovered = []
    panel.launch_requested.connect(lambda item: launched.append(item.name))
    panel.submenu_hovered.connect(hovered.append)
    qtbot.mouseClick(folder, Qt.MouseButton.LeftButton)
    assert launched == []
    local_pos = QPointF(4, 4)
    QApplication.sendEvent(
        folder,
        QEnterEvent(local_pos, local_pos, QPointF(folder.mapToGlobal(QPoint(4, 4)))),
    )
    assert hovered == ["folder"]

    buttons = [button for button in panel._buttons if isinstance(button, LaunchButton)]
    panel._place_launcher_rows([buttons[1], buttons[0]])
    assert isinstance(panel._buttons[0], SubmenuButton)
    assert [button.launcher.name for button in panel._buttons if isinstance(button, LaunchButton)] == [
        "Beta",
        "Alpha",
    ]
    emitted = []
    panel.reordered.connect(emitted.append)
    panel._emit_reordered()
    assert emitted == [[beta.id, alpha.id]]

    local = QPoint(folder.width() // 2, folder.height() // 2)
    QApplication.sendEvent(
        folder,
        QContextMenuEvent(QContextMenuEvent.Reason.Mouse, local, folder.mapToGlobal(local)),
    )
    qapp.processEvents()
    menu = panel._item_menu
    assert menu is not None
    assert [action.text() for action in menu.actions()] == ["Edit", "Delete"]
    edited = []
    panel.submenu_edit_requested.connect(edited.append)
    menu.actions()[0].trigger()
    assert edited == ["folder"]
    menu.close()


def test_container_submenu_launches_the_clicked_row(qapp, qtbot):
    cfg = AppConfig()
    alpha = Launcher.new("Alpha", "open-a")
    panel = DropdownPanel(cfg, honor_pin=False, allow_reorder=False)
    qtbot.addWidget(panel)
    panel.set_heading("Folder")
    panel.rebuild_buttons([alpha])
    panel.show()
    qtbot.waitExposed(panel)
    launched = []
    panel.launch_requested.connect(launched.append)
    button = next(item for item in panel._buttons if isinstance(item, LaunchButton))
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert launched == [alpha]
    assert panel._drag_active is False


def test_container_submenu_opens_beside_the_hovered_row(qapp, qtbot):
    cfg = AppConfig()
    host = DropdownPanel(cfg)
    menu = DropdownPanel(cfg, honor_pin=False, allow_reorder=False)
    qtbot.addWidget(host)
    qtbot.addWidget(menu)
    host.resize(220, 200)
    host.move(300, 80)
    host.show()
    row = SubmenuButton("folder", "Folder", host)
    row.resize(200, 28)
    row.move(8, 40)
    row.show()
    menu.rebuild_buttons([Launcher.new("Alpha", "a")])
    menu.resize(220, 120)
    menu.position_next_to(host, row, prefer_right=True)
    assert menu.x() >= host.x() + host.width()
    assert abs(menu.y() - row.mapToGlobal(QPoint(0, 0)).y()) <= 2
