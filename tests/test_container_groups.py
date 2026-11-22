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
from runner.moves import member_launchers
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


def _v1_launcher(launcher_id, **flags):
    return {"id": launcher_id, "name": launcher_id.title(), "command": launcher_id, **flags}


def test_version_1_flags_fold_into_show_in_main():
    """A v1 launcher was on the main list only when all three old flags agreed."""
    data = {
        "version": 1,
        "launchers": [
            _v1_launcher("alpha"),
            _v1_launcher("beta"),
            _v1_launcher("reserved", only_in_groups=True),
            _v1_launcher("off", enabled=False),
            _v1_launcher("boxed"),
            _v1_launcher("alone"),
        ],
        "container_groups": [
            {"id": "quiet", "name": "Quiet", "members": [
                {"launcher_id": "alpha", "only_in_container": False},
                {"launcher_id": "beta"},
            ]},
            {"id": "loud", "name": "Loud", "members": [
                {"launcher_id": "alpha", "only_in_container": False},
                {"launcher_id": "boxed", "only_in_container": True},
            ]},
        ],
    }
    cfg = AppConfig.from_dict(data)
    shown = {launcher.id: launcher.show_in_main for launcher in cfg.launchers}
    assert shown == {
        "alpha": True,
        "beta": True,
        "reserved": False,
        "off": False,
        # One container switch was enough to hide it.
        "boxed": False,
        # A launcher in no container group stays on the main list.
        "alone": True,
    }
    assert cfg.version == 2
    saved = cfg.to_dict()
    assert all(
        set(item) >= {"show_in_main"} and not {"enabled", "only_in_groups"} & set(item)
        for item in saved["launchers"]
    )
    assert all(
        set(member) == {"launcher_id"}
        for group in saved["container_groups"]
        for member in group["members"]
    )


def test_a_saved_show_in_main_wins_over_old_flags():
    data = {"version": 2, "launchers": [_v1_launcher("alpha", show_in_main=True, only_in_groups=True)]}
    assert AppConfig.from_dict(data).launchers[0].show_in_main is True


def test_container_lists_every_member_in_order_including_hidden_ones():
    first = Launcher.new("First", "first", show_in_main=False)
    second = Launcher.new("Second", "second")
    group = ContainerGroup.new(
        "Apps",
        [ContainerMember(second.id), ContainerMember("missing"), ContainerMember(first.id)],
    )
    assert [item.name for item in member_launchers(group.members, [first, second])] == [
        "Second",
        "First",
    ]


def test_container_groups_roundtrip_and_follow_a_deleted_launcher(tmp_path, monkeypatch):
    mgr = _isolate_config(monkeypatch, tmp_path)
    alpha = Launcher.new("Alpha", "a", show_in_main=False)
    beta = Launcher.new("Beta", "b")
    mgr.add_launcher(alpha)
    mgr.add_launcher(beta)
    mgr.add_container_group(
        ContainerGroup.new("Folder", [ContainerMember(alpha.id), ContainerMember(beta.id)])
    )
    mgr.add_group(Group.new("Run", [GroupMember(alpha.id, concurrent=True)]))

    loaded = ConfigManager()
    assert loaded.config.version == 2
    assert loaded.config.container_groups[0].name == "Folder"
    assert [m.launcher_id for m in loaded.config.container_groups[0].members] == [alpha.id, beta.id]
    assert [item.name for item in loaded.get_main_view_launchers()] == ["Beta"]

    # An old file with no container groups still loads, and those launchers stay visible.
    restored = AppConfig.from_dict({"version": 1, "launchers": [{"id": beta.id, "name": "Beta", "command": "b"}]})
    assert restored.container_groups == []
    assert restored.launchers[0].show_in_main is True

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
        [ContainerMember(beta.id), ContainerMember(alpha.id)],
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

    mgr.set_launcher_membership(alpha.id, [], [later.id])
    assert mgr.config.container_groups[0].members == [ContainerMember(beta.id)]
    assert [member.launcher_id for member in mgr.config.groups[0].members] == [beta.id]
    assert [member.launcher_id for member in mgr.config.groups[1].members] == [alpha.id]


def test_container_dialog_saves_click_order_and_the_switch(qapp, qtbot, tmp_path, monkeypatch):
    mgr = _isolate_config(monkeypatch, tmp_path)
    alpha = Launcher.new("Alpha", "a", show_in_main=False)
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
    # Alpha is already off the main list, so the shared switch starts on.
    assert dialog.only_switch(alpha.id).box.isChecked() is True

    qtbot.mouseClick(dialog.only_switch(alpha.id), Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert dialog.only_switch(alpha.id).box.isChecked() is False
    assert alpha.show_in_main is True

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
    assert [member.launcher_id for member in result.members] == [beta.id, alpha.id]
    # The switch is the launcher's own setting, not stored per container.
    assert alpha.show_in_main is False
    assert beta.show_in_main is True


def test_include_in_dropdown_and_the_group_switches_are_one_setting(
    qapp, qtbot, tmp_path, monkeypatch
):
    mgr = _isolate_config(monkeypatch, tmp_path)
    alpha = Launcher.new("Alpha", "a")
    mgr.add_launcher(alpha)
    folder = ContainerGroup.new("Folder", [ContainerMember(alpha.id)])
    extra = ContainerGroup.new("Extra", [ContainerMember(alpha.id)])
    mgr.add_container_group(folder)
    mgr.add_container_group(extra)
    mgr.add_group(Group.new("Run", [GroupMember(alpha.id)]))

    edit = AddEditDialog(alpha, cfg=mgr)
    qtbot.addWidget(edit)
    assert edit._enabled_cb.isChecked() is True
    edit._enabled_cb.setChecked(False)
    edit.accept()
    assert alpha.show_in_main is False
    assert mgr.get_main_view_launchers() == []

    groups = GroupDialog(mgr, mgr.config.groups[0])
    qtbot.addWidget(groups)
    groups.show()
    qtbot.waitExposed(groups)
    assert groups.only_in_groups_checkbox(alpha.id).box.isChecked() is True
    qtbot.mouseClick(groups.only_in_groups_checkbox(alpha.id), Qt.MouseButton.LeftButton)
    assert alpha.show_in_main is True

    again = AddEditDialog(alpha, cfg=mgr)
    qtbot.addWidget(again)
    assert again._enabled_cb.isChecked() is True

    container = ContainerDialog(mgr, mgr.config.container_groups[0])
    qtbot.addWidget(container)
    container.show()
    qtbot.waitExposed(container)
    assert container.only_switch(alpha.id).box.isChecked() is False
    qtbot.mouseClick(container.only_switch(alpha.id), Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert alpha.show_in_main is False
    final = AddEditDialog(alpha, cfg=mgr)
    qtbot.addWidget(final)
    assert final._enabled_cb.isChecked() is False
    container.close()
    groups.close()


def test_container_and_execute_dialogs_list_launchers_hidden_from_the_main_popup(
    qapp, qtbot, tmp_path, monkeypatch
):
    mgr = _isolate_config(monkeypatch, tmp_path)
    hidden = Launcher.new("Hidden", "hidden", show_in_main=False)
    mgr.add_launcher(hidden)
    mgr.add_container_group(ContainerGroup.new("Folder", [ContainerMember(hidden.id)]))
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
    alpha = Launcher.new("Alpha", "a", show_in_main=False)
    mgr.add_launcher(alpha)
    run = Group.new("Run", [GroupMember(alpha.id, concurrent=True)])
    later = Group.new("Later")
    mgr.add_group(run)
    mgr.add_group(later)
    folder = ContainerGroup.new("Folder", [ContainerMember(alpha.id)])
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
    # Alpha was already off the main popup, and joining a container keeps that choice.
    assert alpha.show_in_main is False
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
    with patch("runner.ui.group_list_manager.question", return_value=QMessageBox.StandardButton.Yes):
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


def _controller(qapp, monkeypatch, tmp_path, *, pinned=False):
    """The real controller over a throwaway config with two containers and one execute group."""
    from unittest.mock import MagicMock

    from runner.controller import RunnerController

    cfg = _isolate_config(monkeypatch, tmp_path)
    alpha, beta = Launcher.new("Alpha", "a"), Launcher.new("Beta", "b")
    cfg.config.launchers = [alpha, beta]
    cfg.config.container_groups = [
        ContainerGroup.new("Projects", [ContainerMember(alpha.id)]),
        ContainerGroup.new("Notes", [ContainerMember(beta.id)]),
    ]
    cfg.config.groups = [Group.new("Class", [GroupMember(alpha.id)])]
    cfg.config.settings.pinned_open = pinned
    cfg.config.settings.position_x, cfg.config.settings.position_y = 400, 500
    monkeypatch.setattr("runner.controller.create_tray", lambda **_: MagicMock())
    ctl = RunnerController(qapp, cfg)
    ctl.greeting.dismiss_for_session()
    return ctl


def _close_all(ctl):
    for panel in ctl._all_lists():
        panel.force_hide()
    ctl.trigger.hide()


def test_container_groups_menu_item_opens_only_the_container_rows(qapp, qtbot, monkeypatch, tmp_path):
    """It opens beside the arrow on its own, as Execute Groups does."""
    ctl = _controller(qapp, monkeypatch, tmp_path)
    ctl.trigger.show()
    try:
        ctl.trigger.request_groups.emit()
        assert ctl.group_panel.isVisible() and not ctl.dropdown.isVisible()
        groups_side = ctl.group_panel.y() < ctl.trigger.y()

        ctl.trigger.request_containers.emit()
        listing = ctl.container_list
        assert listing.isVisible()
        assert not ctl.dropdown.isVisible()
        assert not ctl.group_panel.isVisible()
        assert listing._heading.text() == "Container Groups"
        rows = [b for b in listing._buttons if isinstance(b, SubmenuButton)]
        assert [b.item_name for b in rows] == ["Projects", "Notes"]
        assert not [b for b in listing._buttons if isinstance(b, LaunchButton)]
        # Same side of the arrow as the execute-groups list.
        assert (listing.y() < ctl.trigger.y()) == groups_side
        qtbot.waitUntil(lambda: listing.windowOpacity() >= 0.99, timeout=2000)
    finally:
        _close_all(ctl)


def test_hovering_a_container_row_opens_its_launchers_beside_the_list(qapp, qtbot, monkeypatch, tmp_path):
    ctl = _controller(qapp, monkeypatch, tmp_path)
    ctl.trigger.show()
    try:
        ctl.trigger.request_containers.emit()
        listing = ctl.container_list
        projects = ctl.cfg.config.container_groups[0]
        row = listing.submenu_button(projects.id)
        assert row is not None and row.isVisible()
        listing.submenu_hovered.emit(projects.id)
        panel = ctl.container_panel
        assert panel.isVisible()
        assert ctl.container_menu.open_id == projects.id
        assert [b.launcher.name for b in panel._launch_buttons()] == ["Alpha"]
        assert panel.x() >= listing.x() + listing.width() or panel.x() + panel.width() <= listing.x()
        assert abs(panel.y() - row.mapToGlobal(QPoint(0, 0)).y()) <= 2
    finally:
        _close_all(ctl)


def test_hovering_the_arrow_keeps_the_container_list_until_it_closes(qapp, qtbot, monkeypatch, tmp_path):
    """Like Execute Groups: the arrow reopens the same list until it has closed."""
    ctl = _controller(qapp, monkeypatch, tmp_path)
    ctl.trigger.show()
    try:
        ctl.trigger.request_containers.emit()
        ctl._on_trigger_enter()
        assert ctl.container_list.isVisible() and not ctl.dropdown.isVisible()

        ctl.container_list.force_hide()
        assert ctl.mode.name == "MAIN"
        ctl._on_trigger_enter()
        assert ctl.dropdown.isVisible() and not ctl.container_list.isVisible()
    finally:
        _close_all(ctl)


def test_dragging_the_arrow_reopens_the_container_list_on_the_drop(qapp, qtbot, monkeypatch, tmp_path):
    ctl = _controller(qapp, monkeypatch, tmp_path)
    ctl.trigger.show()
    try:
        ctl.trigger.request_containers.emit()
        ctl.trigger.drag_started.emit()
        assert not ctl.container_list.isVisible()
        ctl.trigger.drag_finished.emit()
        assert ctl.container_list.isVisible() and not ctl.dropdown.isVisible()
    finally:
        _close_all(ctl)


def test_pinned_main_popup_returns_after_the_container_list_closes(qapp, qtbot, monkeypatch, tmp_path):
    ctl = _controller(qapp, monkeypatch, tmp_path, pinned=True)
    ctl.trigger.show()
    try:
        ctl._apply_pinned_state()
        assert ctl.dropdown.isVisible()
        ctl.trigger.request_containers.emit()
        assert ctl.container_list.isVisible() and not ctl.dropdown.isVisible()
        ctl.container_list.force_hide()
        assert ctl.dropdown.isVisible()
    finally:
        _close_all(ctl)


def test_container_groups_with_none_saved_opens_nothing(qapp, qtbot, monkeypatch, tmp_path):
    ctl = _controller(qapp, monkeypatch, tmp_path)
    ctl.cfg.config.container_groups = []
    ctl.trigger.show()
    try:
        ctl.trigger.request_containers.emit()
        assert not ctl.container_list.isVisible()
        assert ctl.mode.name == "MAIN"
    finally:
        _close_all(ctl)


def test_a_late_leave_from_the_closed_main_list_keeps_the_container_list(qapp, qtbot, monkeypatch, tmp_path):
    """macOS can report the pointer leaving a list after that list was closed."""
    ctl = _controller(qapp, monkeypatch, tmp_path)
    ctl.trigger.show()
    try:
        ctl._on_trigger_enter()
        assert ctl.dropdown.isVisible()
        ctl.trigger.request_containers.emit()
        assert not ctl.dropdown.isVisible()
        ctl.dropdown.hover_leave.emit()
        assert not ctl.hide_timer.isActive()
        assert ctl.container_list.isVisible()
    finally:
        _close_all(ctl)
