"""Groups of launchers: order, concurrency, dialogs, and the arrow menu."""

from unittest.mock import patch

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QContextMenuEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QMessageBox, QPushButton

from runner.config import AppConfig, ConfigManager, Group, GroupMember, Launcher
from runner.groups import (
    display_order,
    execution_steps,
    run_group_steps,
    select_member,
    selected_order_after_drag,
    unselect_member,
)
from runner.ui.add_dialog import AddEditDialog
from runner.ui.dropdown import DropdownPanel, LockedPairMotion, _HIDE_DECAY_MS
from runner.ui.group_dialog import GroupDialog, _NOTE, _SELECTED_BG
from runner.ui.group_manager import GroupManagerDialog
from runner.ui.launch_button import LaunchButton
from runner.ui.toggle_switch import ToggleSwitch
from runner.ui.trigger import TriggerWidget


def _isolate_config(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "runner.config.platformdirs.user_config_dir",
        lambda *a, **k: str(tmp_path),
    )
    return ConfigManager()


def _launchers(*names: str, **flags) -> list[Launcher]:
    return [Launcher.new(name, name.lower(), **flags) for name in names]


def test_selection_order_follows_clicks_and_snaps_back():
    base = ["a", "b", "c", "d"]
    selected = select_member(base, [], "c")
    selected = select_member(base, selected, "a")
    assert selected == ["c", "a"]
    assert display_order(base, selected) == ["c", "a", "b", "d"]

    selected = unselect_member(selected, "c")
    assert display_order(base, selected) == ["a", "b", "c", "d"]

    # A second check does not move an item that is already selected.
    assert select_member(base, ["c", "a"], "c") == ["c", "a"]
    # Dragging the checked rows swaps them. Unchecked rows are ignored.
    assert selected_order_after_drag(["a", "d", "c", "b"], ["c", "a"]) == ["a", "c"]


def test_execution_steps_match_the_preschool_example():
    items = _launchers("1", "2", "3", "4", "5", "6", "7", "8", "9", "10")
    # 2-5 start together. 1 and 6-10 each start on their own.
    concurrent = {items[index].id for index in (1, 2, 3, 4)}
    group = Group.new(
        "Teaching Pre-School Class One",
        [
            GroupMember(item.id, concurrent=item.id in concurrent)
            for item in items
        ],
    )
    steps = execution_steps(group, items)
    assert [[item.name for item in step] for step in steps] == [
        ["1"],
        ["2", "3", "4", "5"],
        ["6"],
        ["7"],
        ["8"],
        ["9"],
        ["10"],
    ]


def test_execution_runs_launchers_hidden_from_the_main_list_and_skips_missing_ids():
    shown = Launcher.new("Shown", "shown")
    hidden = Launcher.new("Hidden", "hidden", show_in_main=False)
    group = Group.new(
        "Mix",
        [
            GroupMember(shown.id),
            GroupMember("missing"),
            GroupMember(hidden.id, concurrent=True),
        ],
    )
    steps = execution_steps(group, [shown, hidden])
    assert [[item.name for item in step] for step in steps] == [["Shown"], ["Hidden"]]


def test_run_group_steps_waits_between_steps_and_keeps_going_after_an_error():
    items = _launchers("one", "two", "three")
    steps = [[items[0]], [items[1], items[2]]]
    pending = []
    started = []
    errors = []
    finished = []

    def schedule(delay, callback):
        pending.append((delay, callback))

    def launch_one(item):
        started.append(item.name)
        if item.name == "two":
            raise RuntimeError("boom")

    run_group_steps(
        steps,
        launch_one,
        schedule,
        gap_ms=300,
        on_error=lambda item, exc: errors.append((item.name, str(exc))),
        on_finished=lambda: finished.append("done"),
    )
    assert started == ["one"]
    assert finished == []
    assert pending[0][0] == 300
    pending.pop(0)[1]()
    assert started == ["one", "two", "three"]
    assert errors == [("two", "boom")]
    assert finished == ["done"]
    assert pending == []


def test_step_timer_can_be_tied_to_a_widget(qapp, qtbot):
    """The group runner schedules the next step with QTimer.singleShot(ms, receiver, fn)."""
    seen = []
    owner = QObject()
    QTimer.singleShot(0, owner, lambda: seen.append("ok"))
    qtbot.waitUntil(lambda: seen == ["ok"], timeout=1000)


def test_config_roundtrip_and_removing_a_launcher_strips_group_members(tmp_path, monkeypatch):
    mgr = _isolate_config(monkeypatch, tmp_path)
    alpha = Launcher.new("Alpha", "a", show_in_main=False)
    beta = Launcher.new("Beta", "b")
    mgr.add_launcher(alpha)
    mgr.add_launcher(beta)
    group = Group.new("Class", [GroupMember(alpha.id, concurrent=True), GroupMember(beta.id)])
    mgr.add_group(group)

    loaded = ConfigManager()
    assert loaded.config.version == 2
    assert loaded.config.groups[0].name == "Class"
    assert loaded.config.groups[0].members[0].concurrent is True
    assert loaded.config.launchers[0].show_in_main is False
    assert [item.name for item in loaded.get_main_view_launchers()] == ["Beta"]

    loaded.remove_launcher(alpha.id)
    assert loaded.config.groups[0].members == [GroupMember(beta.id)]

    old = {"version": 1, "settings": {"dropdown_width": 200}, "launchers": [{"id": "x", "name": "X", "command": "x"}]}
    restored = AppConfig.from_dict(old)
    assert restored.groups == []
    assert restored.launchers[0].show_in_main is True
    assert restored.version == 2


def test_show_group_contents_defaults_off_and_saves_with_the_group(qapp, qtbot, tmp_path, monkeypatch):
    mgr = _isolate_config(monkeypatch, tmp_path)
    group = Group.new("Morning")
    assert group.show_contents is False
    mgr.add_group(group)

    edit = GroupDialog(mgr, group)
    qtbot.addWidget(edit)
    edit.show()
    assert edit.windowTitle() == "Edit Execute Group"
    qtbot.waitExposed(edit)
    assert edit._show_contents.text() == "Show group contents"
    assert edit._show_contents.isChecked() is False
    qtbot.mouseClick(edit._show_contents, Qt.MouseButton.LeftButton)
    assert edit._show_contents.isChecked() is True
    edit.accept()
    assert group.show_contents is True
    mgr.update_group(group)
    assert ConfigManager().config.groups[0].show_contents is True

    again = GroupDialog(mgr, ConfigManager().config.groups[0])
    qtbot.addWidget(again)
    assert again._show_contents.isChecked() is True
    again._show_contents.setChecked(False)
    again.accept()
    assert again.result_group is not None
    assert again.result_group.show_contents is False

    old = {"version": 1, "groups": [{"id": "g1", "name": "Class", "members": []}]}
    assert AppConfig.from_dict(old).groups[0].show_contents is False
    junk = {
        "version": 1,
        "groups": [{"id": "g2", "name": "Class", "members": [], "show_contents": "yes"}],
    }
    assert AppConfig.from_dict(junk).groups[0].show_contents is False


def test_reorder_groups_keeps_unknown_ids(tmp_path, monkeypatch):
    mgr = _isolate_config(monkeypatch, tmp_path)
    first = Group.new("First")
    second = Group.new("Second")
    mgr.add_group(first)
    mgr.add_group(second)
    mgr.reorder_groups([second.id])
    assert [group.name for group in mgr.config.groups] == ["Second", "First"]


def test_group_dialog_checks_in_click_order_and_shares_only_in_groups(qapp, qtbot, tmp_path, monkeypatch):
    mgr = _isolate_config(monkeypatch, tmp_path)
    alpha, beta, gamma = _launchers("Alpha", "Beta", "Gamma")
    for launcher in (alpha, beta, gamma):
        mgr.add_launcher(launcher)

    dialog = GroupDialog(mgr, None)
    qtbot.addWidget(dialog)
    dialog.show()
    assert dialog.windowTitle() == "Add Execute Group"
    qtbot.waitExposed(dialog)
    headers = [dialog._table.horizontalHeaderItem(column).text() for column in range(3)]
    assert headers == ["Launcher", "Concurrent", "Only In Groups"]
    notes = [label.text() for label in dialog.findChildren(QLabel)]
    assert _NOTE in notes
    assert dialog._show_contents.text() == "Show group contents"
    assert dialog._show_contents.isChecked() is False
    assert [button.text() for button in dialog.findChildren(QPushButton)] == [
        "Add new Launcher",
        "Save",
        "Cancel",
    ]
    assert dialog.display_ids() == [alpha.id, beta.id, gamma.id]

    def click_name(launcher_id):
        cell = dialog.name_cell(launcher_id)
        assert cell.width() > 80
        qtbot.mouseClick(cell, Qt.MouseButton.LeftButton)
        qapp.processEvents()

    # Click the name, not the tiny checkbox indicator. Later clicks stay in that order.
    click_name(gamma.id)
    selected_cells = [
        dialog.name_cell(gamma.id),
        dialog.concurrent_checkbox(gamma.id),
        dialog.only_in_groups_checkbox(gamma.id),
    ]
    for cell in selected_cells:
        assert _SELECTED_BG in cell.styleSheet()
    for column in range(3):
        assert dialog._table.item(0, column).background().color().name() == _SELECTED_BG
    assert _SELECTED_BG not in dialog.name_cell(alpha.id).styleSheet()
    click_name(alpha.id)
    assert dialog.display_ids() == [gamma.id, alpha.id, beta.id]
    assert dialog.name_cell(gamma.id).box.isChecked() is True
    assert dialog.name_cell(alpha.id).box.isChecked() is True
    assert dialog.name_cell(beta.id).box.isChecked() is False

    click_name(gamma.id)
    assert dialog.display_ids() == [alpha.id, beta.id, gamma.id]
    assert dialog.name_cell(gamma.id).box.isChecked() is False

    qtbot.mouseClick(dialog.concurrent_checkbox(beta.id), Qt.MouseButton.LeftButton)
    click_name(beta.id)
    assert dialog.display_ids() == [alpha.id, beta.id, gamma.id]
    assert dialog.concurrent_checkbox(beta.id).box.isChecked() is True

    click_name(beta.id)
    assert dialog.name_cell(beta.id).box.isChecked() is False
    assert dialog.concurrent_checkbox(beta.id).box.isChecked() is False
    click_name(beta.id)
    assert dialog.name_cell(beta.id).box.isChecked() is True
    assert dialog.concurrent_checkbox(beta.id).box.isChecked() is False
    qtbot.mouseClick(dialog.concurrent_checkbox(beta.id), Qt.MouseButton.LeftButton)
    assert dialog.concurrent_checkbox(beta.id).box.isChecked() is True

    dialog._on_visual_order([beta.id, alpha.id, gamma.id])
    qapp.processEvents()
    assert dialog._selected == [beta.id, alpha.id]
    assert dialog.display_ids() == [beta.id, alpha.id, gamma.id]

    qtbot.mouseClick(dialog.only_in_groups_checkbox(alpha.id), Qt.MouseButton.LeftButton)
    assert alpha.show_in_main is False
    reloaded = ConfigManager()
    assert reloaded.config.launchers[0].show_in_main is False
    edit = AddEditDialog(reloaded.config.launchers[0])
    qtbot.addWidget(edit)
    assert edit._enabled_cb.text() == "Include in dropdown list"
    assert edit._enabled_cb.isChecked() is False
    assert not hasattr(edit, "_only_in_groups_cb")

    dialog._name_edit.setText("  ")
    with patch("runner.ui.group_dialog.warning") as warn:
        dialog.accept()
    warn.assert_called_once()
    assert dialog.result_group is None

    dialog._name_edit.setText("Teaching Pre-School Class One")
    dialog.accept()
    result = dialog.result_group
    assert result is not None
    assert result.name == "Teaching Pre-School Class One"
    assert result.show_contents is False
    assert [(member.launcher_id, member.concurrent) for member in result.members] == [
        (beta.id, True),
        (alpha.id, False),
    ]


def test_dragging_a_highlighted_launcher_changes_run_order(qapp, qtbot, tmp_path, monkeypatch):
    mgr = _isolate_config(monkeypatch, tmp_path)
    alpha, beta = _launchers("Alpha", "Beta")
    mgr.add_launcher(alpha)
    mgr.add_launcher(beta)
    dialog = GroupDialog(mgr)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)

    qtbot.mouseClick(dialog.name_cell(alpha.id), Qt.MouseButton.LeftButton)
    qapp.processEvents()
    qtbot.mouseClick(dialog.name_cell(beta.id), Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert dialog._selected == [alpha.id, beta.id]

    first = dialog.name_cell(alpha.id)
    press_at = first.mapToGlobal(first.rect().center())
    second = dialog.name_cell(beta.id)
    below = second.mapToGlobal(second.rect().center())
    below.setY(below.y() + 8)

    _send_mouse(first, QEvent.Type.MouseButtonPress, press_at, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    _send_mouse(first, QEvent.Type.MouseMove, below, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    assert dialog._drag_id == alpha.id
    ghost = dialog._ghost
    assert ghost is not None and ghost.isVisible() and not ghost.isWindow()
    assert ghost.label.text() == "Alpha"
    assert ghost.width() == dialog._table.viewport().width()
    assert dialog.mapToGlobal(ghost.pos()) + dialog._drag_hotspot == below
    ghost.repaint()
    edge = ghost.grab().toImage().pixelColor(2, 2)
    assert edge.red() > 240 and edge.green() > 190 and edge.blue() < 40, edge.name()
    faded = dialog.name_cell(alpha.id).graphicsEffect()
    assert faded is not None and faded.opacity() < 0.5
    _send_mouse(first, QEvent.Type.MouseButtonRelease, below, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    qapp.processEvents()
    assert dialog._ghost is None
    assert dialog._selected == [beta.id, alpha.id]
    assert dialog.display_ids()[:2] == [beta.id, alpha.id]


def test_manage_groups_deletes_the_group_and_keeps_its_launchers(qapp, qtbot, tmp_path, monkeypatch):
    mgr = _isolate_config(monkeypatch, tmp_path)
    launcher = Launcher.new("Alpha", "a")
    mgr.add_launcher(launcher)
    mgr.add_group(Group.new("Class", [GroupMember(launcher.id)]))

    dialog = GroupManagerDialog(mgr)
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Manage Execute Groups"
    assert dialog._list.item(0).text() == "Class  (1 launcher)"
    dialog._list.setCurrentRow(0)
    with patch("runner.ui.group_list_manager.question", return_value=QMessageBox.StandardButton.Yes):
        dialog._on_delete()
    assert dialog._list.count() == 0
    assert [item.name for item in mgr.config.launchers] == ["Alpha"]
    assert mgr.config.groups == []


def _arrow_menu(trigger):
    found = [
        menu
        for menu in trigger.findChildren(QMenu)
        if any(action.text() == "Exit" for action in menu.actions())
    ]
    assert found
    return found[-1]


def test_arrow_menu_puts_group_actions_above_exit(qapp, qtbot):
    trigger = TriggerWidget(AppConfig())
    qtbot.addWidget(trigger)
    seen = []
    trigger.request_add_group.connect(lambda: seen.append("add"))
    trigger.request_manage_groups.connect(lambda: seen.append("manage"))
    trigger.request_groups.connect(lambda: seen.append("groups"))

    trigger._show_context_menu(QPoint(8, 8))
    menu = _arrow_menu(trigger)
    qtbot.addWidget(menu)
    labels = [
        "---" if action.isSeparator() else action.text()
        for action in menu.actions()
        if action.isSeparator() or action.text()
    ]
    assert labels[-14:] == [
        "---",
        "Execute Groups",
        "Container Groups",
        "Add Execute Group",
        "Add Container Group",
        "Manage Execute Groups",
        "Manage Container Groups",
        "---",
        "Opacity",
        "Decay rate",
        "---",
        "Color Schemes",
        "---",
        "Exit",
    ]

    trigger._action_add_group.trigger()
    trigger._action_manage_groups.trigger()
    trigger._action_groups.trigger()
    assert seen == ["add", "manage", "groups"]
    menu.close()


def test_show_groups_switch_sits_under_the_greeting_switch(qapp, qtbot):
    cfg = AppConfig()
    assert cfg.settings.show_groups is False
    loaded = AppConfig.from_dict({"version": 1, "settings": {"position_x": 4}, "launchers": []})
    assert loaded.settings.show_groups is False

    trigger = TriggerWidget(cfg)
    qtbot.addWidget(trigger)
    seen = []
    trigger.groups_toggled.connect(seen.append)
    trigger._show_context_menu(QPoint(8, 8))
    menu = _arrow_menu(trigger)
    qtbot.addWidget(menu)
    names = [switch.text() for switch in menu.findChildren(ToggleSwitch)]
    assert names.index("Show execute groups") == names.index("Show greeting message") + 1
    switch = next(item for item in menu.findChildren(ToggleSwitch) if item.text() == "Show execute groups")
    assert switch.isChecked() is False
    switch.click()
    assert seen == [True]
    menu.close()


class _Screen:
    def availableGeometry(self):
        return QRect(0, 0, 1920, 1080)


class _Arrow:
    def __init__(self, x: int) -> None:
        self._x = x

    def mapToGlobal(self, _point):
        return QPoint(self._x, 40)

    def width(self) -> int:
        return 40


def test_empty_groups_list_shows_no_message(qapp, qtbot):
    panel = DropdownPanel(AppConfig(), honor_pin=False)
    qtbot.addWidget(panel)
    panel.set_list_copy(placeholder="Filter execute groups...", empty_hint="")
    panel.set_heading("Groups")
    panel.rebuild_buttons([])
    labels = [widget for widget in panel._buttons if isinstance(widget, QLabel)]
    assert labels == []
    assert "No groups" not in panel._empty_hint

    added = Launcher.new("Morning", "")
    panel.rebuild_buttons([added])
    names = [button.launcher.name for button in panel._buttons if isinstance(button, LaunchButton)]
    assert names == ["Morning"]


def test_groups_list_opens_beside_launchers_toward_the_middle(qapp, qtbot):
    cfg = AppConfig()
    launchers = DropdownPanel(cfg)
    groups = DropdownPanel(cfg, honor_pin=False)
    groups.set_heading("Execute Groups")
    qtbot.addWidget(launchers)
    qtbot.addWidget(groups)
    assert groups._heading.text() == "Execute Groups"
    assert groups._heading.isHidden() is False
    assert "11px" in groups._heading.styleSheet()
    assert groups._layout.indexOf(groups._heading) < groups._layout.indexOf(groups._search_edit)

    launchers.rebuild_buttons([Launcher.new("Alpha", "a")])
    groups.rebuild_buttons([Launcher.new("Class", "")])
    launchers.show()
    groups.show()
    qapp.processEvents()

    def place(arrow_x: int) -> None:
        with patch("runner.ui.dropdown.QApplication.screenAt", return_value=_Screen()):
            groups.position_beside(launchers, _Arrow(arrow_x))

    launchers.move(1400, 80)
    launchers._grow_from_top = True
    place(1600)
    assert groups.x() + groups.width() <= launchers.x()
    assert groups.y() == launchers.y()
    assert groups._grow_from_top is True

    launchers.move(80, 80)
    launchers._grow_from_top = True
    place(40)
    assert groups.x() >= launchers.x() + launchers.width()
    assert groups.y() == launchers.y()

    launchers.move(1400, 700)
    launchers._grow_from_top = False
    launchers._fixed_edge_y = launchers.y() + launchers.height()
    place(1600)
    assert groups._grow_from_top is False
    assert groups.y() + groups.height() == launchers._fixed_edge_y
    assert groups.x() + groups.width() <= launchers.x()


def _send_mouse(button, kind, global_pos, button_state, buttons_state):
    local = button.mapFromGlobal(global_pos)
    event = QMouseEvent(
        kind,
        QPointF(local),
        QPointF(global_pos),
        button_state,
        buttons_state,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(button, event)


def test_add_new_launcher_appears_unchecked_for_the_group(qapp, tmp_path, monkeypatch):
    mgr = _isolate_config(monkeypatch, tmp_path)
    existing = Launcher.new("Alpha", "a")
    mgr.add_launcher(existing)
    dialog = GroupDialog(mgr)
    created = Launcher.new("New", "new")

    class _FakeDialog:
        result_launcher = created

        def exec(self):
            return True

    with patch("runner.ui.member_dialog.AddEditDialog", return_value=_FakeDialog()):
        dialog._on_add_launcher()
    assert dialog.display_ids() == [existing.id, created.id]
    assert dialog._selected == []
    assert [item.name for item in mgr.config.launchers] == ["Alpha", "New"]


def test_edit_drops_launchers_that_no_longer_exist(qapp, tmp_path, monkeypatch):
    mgr = _isolate_config(monkeypatch, tmp_path)
    keep = Launcher.new("Keep", "keep")
    mgr.add_launcher(keep)
    group = Group.new("Class", [GroupMember("gone", concurrent=True), GroupMember(keep.id)])
    dialog = GroupDialog(mgr, group)
    assert dialog._selected == [keep.id]
    dialog.accept()
    result = dialog.result_group
    assert result is not None
    assert [member.launcher_id for member in result.members] == [keep.id]


def test_a_forced_hide_stays_hidden_when_hover_would_restore_a_fade(qapp, qtbot):
    cfg = AppConfig()
    panel = DropdownPanel(cfg, honor_pin=False)
    qtbot.addWidget(panel)
    panel.rebuild_buttons([Launcher.new("Alpha", "a")])
    panel.resize(220, 160)
    panel.show()
    qtbot.waitExposed(panel)

    panel.start_hide_animation()
    panel.force_hide()
    panel.cancel_close()
    assert panel.isVisible() is False
    assert panel.is_closing() is False


def test_decay_rate_is_how_long_the_close_fade_lasts(qapp, qtbot):
    cfg = AppConfig()
    cfg.settings.decay_ms = 80
    panel = DropdownPanel(cfg, honor_pin=False)
    qtbot.addWidget(panel)
    panel.rebuild_buttons([Launcher.new("Alpha", "a")])
    panel.resize(220, 160)
    panel.show()
    qtbot.waitExposed(panel)
    panel.start_hide_animation()
    assert {anim.duration() for anim in panel._anims} == {80}

    cfg.settings.decay_ms = 0
    panel.force_hide()
    panel.show()
    qtbot.waitExposed(panel)
    closed = []
    panel.closed.connect(lambda: closed.append("closed"))
    panel.start_hide_animation()
    assert panel.isVisible() is False
    assert closed == ["closed"]


def test_showing_again_cancels_a_hide_that_is_already_running(qapp, qtbot):
    cfg = AppConfig()
    cfg.settings.animation_duration_ms = 400
    panel = DropdownPanel(cfg, honor_pin=False)
    qtbot.addWidget(panel)
    panel.rebuild_buttons([Launcher.new("Alpha", "a")])
    panel.resize(220, 160)
    panel.show()
    qtbot.waitExposed(panel)
    closed = []
    panel.closed.connect(lambda: closed.append("closed"))

    panel.start_hide_animation()
    assert panel.is_closing() is True
    panel.start_show_animation()
    assert panel.is_closing() is False
    qtbot.wait(500)
    assert panel.isVisible() is True
    assert closed == []


def test_close_decays_for_a_quarter_second_and_can_be_restored(qapp, qtbot):
    cfg = AppConfig()
    cfg.settings.animation_duration_ms = 180
    panel = DropdownPanel(cfg, honor_pin=False)
    qtbot.addWidget(panel)
    panel.rebuild_buttons([Launcher.new("Alpha", "a")])
    panel.resize(220, 160)
    panel.show()
    qtbot.waitExposed(panel)
    closed = []
    panel.closed.connect(lambda: closed.append("closed"))

    panel.start_show_animation()
    assert panel._anims
    assert {anim.duration() for anim in panel._anims} == {180}
    qtbot.wait(220)

    height_before = panel._frame.height()
    pos_before = panel.pos()
    panel.start_hide_animation()
    assert panel.is_closing() is True
    assert [bytes(anim.propertyName()) for anim in panel._anims] == [b"windowOpacity"]
    assert {anim.duration() for anim in panel._anims} == {_HIDE_DECAY_MS}
    qtbot.wait(40)
    assert panel._frame.height() == height_before
    assert panel.pos() == pos_before
    panel.cancel_close()
    assert panel.is_closing() is False
    assert panel.isVisible() is True
    assert panel.windowOpacity() == 1.0
    qtbot.wait(_HIDE_DECAY_MS + 80)
    assert closed == []
    assert panel.isVisible() is True


def test_group_list_matches_the_main_view_and_reorders_groups_only(qapp, qtbot):
    cfg = AppConfig()
    cfg.settings.pinned_open = True
    real = Launcher.new("Real", "real")
    cfg.launchers = [real]
    panel = DropdownPanel(cfg, honor_pin=False)
    qtbot.addWidget(panel)
    main = DropdownPanel(cfg)
    qtbot.addWidget(main)
    assert panel._frame.styleSheet() == main._frame.styleSheet()

    order = ["g1", "g2"]
    panel.set_order_ids(lambda: list(order))
    panel.set_list_copy(placeholder="Filter groups...", empty_hint="No groups yet.")
    panel.set_row_tooltip(lambda row: f"Run group: {row.name}")
    one = Launcher(id="g1", name="One", command="")
    two = Launcher(id="g2", name="Two", command="")
    panel.rebuild_buttons([one, two])
    panel.resize(220, 200)
    panel.show()
    qtbot.waitExposed(panel)
    QApplication.processEvents()

    buttons = [button for button in panel._buttons if isinstance(button, LaunchButton)]
    assert buttons[0].toolTip() == "Run group: One"
    assert [action.text() for action in _row_menu(panel, buttons[1]).actions()] == ["Edit", "Delete"]

    reordered = []
    panel.reordered.connect(lambda ids: (order.clear(), order.extend(ids), reordered.append(list(ids))))
    top = buttons[1]
    press_at = top.mapToGlobal(top.rect().center())
    above = buttons[0].mapToGlobal(buttons[0].rect().topLeft())
    above.setY(above.y() - 4)
    try:
        _send_mouse(top, QEvent.Type.MouseButtonPress, press_at, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
        _send_mouse(top, QEvent.Type.MouseMove, above, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
        _send_mouse(top, QEvent.Type.MouseButtonRelease, above, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    finally:
        panel._cancel_drag()

    assert reordered == [["g2", "g1"]]
    assert [item.id for item in cfg.launchers] == [real.id]

    closed = []
    panel.closed.connect(lambda: closed.append("closed"))
    panel.start_hide_animation()
    qtbot.waitUntil(lambda: closed == ["closed"], timeout=2000)
    assert panel.isVisible() is False


def test_arrow_hover_locks_main_popup_and_execute_groups(qapp, qtbot):
    """The two lists share one fade. Neither grows, shrinks, or moves while it fades."""
    cfg = AppConfig()
    main_panel = DropdownPanel(cfg)
    groups = DropdownPanel(cfg, honor_pin=False)
    qtbot.addWidget(main_panel)
    qtbot.addWidget(groups)
    main_panel.rebuild_buttons([Launcher.new(f"L{i}", "x") for i in range(12)])
    groups.set_heading("Execute Groups")
    groups.rebuild_buttons([Launcher.new("Class", "")])

    def place_main() -> None:
        main_panel.move(120, 80)
        main_panel._grow_from_top = True
        main_panel._fixed_edge_y = 80

    def place_groups() -> None:
        groups.move(main_panel.x() + main_panel.width() + 6, 80)
        groups._grow_from_top = True
        groups._fixed_edge_y = 80

    main_panel.use_position_hook(place_main)
    groups.use_position_hook(place_groups)
    motion = LockedPairMotion(main_panel, lambda: 600, hide_duration_ms=600)
    main_panel.set_locked_pair(motion)
    groups.set_locked_pair(motion)
    samples: list[tuple[float, float]] = []
    motion._anim.valueChanged.connect(
        lambda _value: samples.append((main_panel._linked_fraction, groups._linked_fraction))
    )

    motion.open([main_panel, groups])
    assert main_panel._linked_full_h > groups._linked_full_h
    assert main_panel._linked_fraction == groups._linked_fraction

    def _full_size_in_place() -> None:
        assert main_panel._frame.height() == main_panel._linked_full_h
        assert groups._frame.height() == groups._linked_full_h
        assert main_panel.y() == 80 and groups.y() == 80

    def _locked_open() -> bool:
        fraction = main_panel._linked_fraction
        if not 0.08 < fraction < 0.9 or abs(fraction - groups._linked_fraction) > 0.001:
            return False
        _full_size_in_place()
        return (abs(main_panel.windowOpacity() - fraction) < 0.02
                and abs(groups.windowOpacity() - fraction) < 0.02)

    qtbot.waitUntil(_locked_open, timeout=2000)
    assert samples
    for left, right in samples:
        assert abs(left - right) < 0.001

    seen = motion.progress()
    motion.close([main_panel, groups])
    assert main_panel.is_closing() is True
    assert groups.is_closing() is True
    assert abs(main_panel._linked_fraction - groups._linked_fraction) < 0.001
    assert motion.progress() <= seen + 0.02

    def _locked_close() -> bool:
        fraction = main_panel._linked_fraction
        if not motion.is_closing() or not (0.02 < motion.progress() < seen):
            return False
        if abs(fraction - groups._linked_fraction) > 0.001:
            return False
        _full_size_in_place()
        return (abs(main_panel.windowOpacity() - fraction) < 0.02
                and abs(groups.windowOpacity() - fraction) < 0.02)

    qtbot.waitUntil(_locked_close, timeout=2000)
    # Moving onto one list must restore both. One list must not finish closing alone.
    main_panel.cancel_close()
    assert motion.is_closing() is False
    assert main_panel.is_closing() is False
    assert groups.is_closing() is False
    assert main_panel.isVisible() is True
    assert groups.isVisible() is True
    assert main_panel._linked_fraction == 1.0
    assert groups._linked_fraction == 1.0


def test_leave_locks_lists_that_opened_apart(qapp, qtbot):
    """A hover close still matches the two lists if they were not opened together."""
    cfg = AppConfig()
    main_panel = DropdownPanel(cfg)
    groups = DropdownPanel(cfg, honor_pin=False)
    qtbot.addWidget(main_panel)
    qtbot.addWidget(groups)
    main_panel.rebuild_buttons([Launcher.new("Alpha", "a"), Launcher.new("Beta", "b")])
    groups.rebuild_buttons([Launcher.new("Class", "")])
    main_panel.use_position_hook(lambda: (main_panel.move(40, 40), setattr(main_panel, "_fixed_edge_y", 40)))
    groups.use_position_hook(lambda: (groups.move(280, 40), setattr(groups, "_fixed_edge_y", 40)))
    main_panel.show()
    groups.show()
    main_panel._update_height_for_content()
    groups._update_height_for_content()
    main_panel.setWindowOpacity(1.0)
    groups.setWindowOpacity(0.4)
    motion = LockedPairMotion(main_panel, lambda: 400, hide_duration_ms=400)
    samples: list[tuple[float, float]] = []
    motion._anim.valueChanged.connect(
        lambda _value: samples.append((main_panel._linked_fraction, groups._linked_fraction))
    )
    assert motion.close_visible([main_panel, groups]) is True
    assert abs(main_panel._linked_fraction - groups._linked_fraction) < 0.001
    assert abs(main_panel._linked_fraction - 0.4) < 0.001
    assert motion.is_closing() is True
    qtbot.waitUntil(lambda: not motion.is_running() and not main_panel.isVisible(), timeout=2000)
    assert samples
    for left, right in samples:
        assert abs(left - right) < 0.001
    assert groups.isVisible() is False


def _row_menu(panel: DropdownPanel, button: LaunchButton) -> QMenu:
    local = QPoint(button.width() // 2, button.height() // 2)
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, local, button.mapToGlobal(local))
    QApplication.sendEvent(button, event)
    QApplication.processEvents()
    menu = panel._item_menu
    assert menu is not None
    return menu


def test_lists_stay_solid_whatever_the_opacity_slider_says(qapp, qtbot):
    """The Opacity slider is for the arrow. A list at rest is always solid."""
    cfg = AppConfig()
    cfg.settings.opacity_percent = 30
    panel = DropdownPanel(cfg)
    qtbot.addWidget(panel)
    panel.rebuild_buttons([Launcher.new("Alpha", "a")])
    panel.start_show_animation(focus=False)
    qtbot.waitUntil(lambda: panel.windowOpacity() >= 0.999, timeout=2000)
    panel.ensure_visible_and_sized()
    assert panel.windowOpacity() >= 0.999


def test_a_list_fades_in_at_full_size_and_in_place(qapp, qtbot):
    """Opening above the arrow used to grow upward from it. Now it only fades."""
    cfg = AppConfig()
    panel = DropdownPanel(cfg)
    qtbot.addWidget(panel)
    panel.rebuild_buttons([Launcher.new(f"L{i}", "x") for i in range(8)])

    def place_above() -> None:
        panel._grow_from_top = False
        panel._fixed_edge_y = 600
        panel.move(100, 600 - panel.height())

    panel.use_position_hook(place_above)
    poses: list[tuple[int, int, float]] = []
    timer = QTimer()
    timer.setInterval(5)
    timer.timeout.connect(lambda: poses.append((panel.y(), panel._frame.height(), panel.windowOpacity())))
    panel.start_show_animation(focus=False)
    full = (panel.y(), panel._frame.height())
    timer.start()
    qtbot.waitUntil(lambda: panel.windowOpacity() >= 0.999, timeout=2000)
    timer.stop()
    assert panel.y() + panel.height() == 600
    partly = [pose for pose in poses if 0.05 < pose[2] < 0.95]
    assert partly, "the fade should have been caught part way"
    assert {(y, h) for y, h, _ in poses} == {full}


def test_reset_label_reads_position_and_size(qapp, qtbot):
    """'&' in a menu label marks a shortcut and is not shown, which left a double space."""
    trigger = TriggerWidget(AppConfig())
    qtbot.addWidget(trigger)
    trigger._show_context_menu(QPoint(8, 8))
    qapp.processEvents()
    menus = [m for m in trigger.findChildren(QMenu) if any(a.text() == "Exit" for a in m.actions())]
    menu = menus[-1]
    qtbot.addWidget(menu)
    texts = [action.text() for action in menu.actions()]
    assert "Reset position and size" in texts
    assert not any("&" in text for text in texts)
    menu.close()


def test_a_list_a_little_over_420px_opens_without_a_scrollbar(qapp, qtbot):
    """The list used to stop at 420 px and scroll the last few pixels."""
    cfg = AppConfig()
    arrow = QLabel("arrow")
    qtbot.addWidget(arrow)
    arrow.resize(60, 40)
    screen = QApplication.primaryScreen().availableGeometry()
    arrow.move(screen.left() + 40, screen.top() + 10)
    arrow.show()
    panel = DropdownPanel(cfg)
    qtbot.addWidget(panel)
    panel.rebuild_buttons([Launcher.new(f"L{i}", "x") for i in range(14)])  # ~440 px of rows
    panel.position_adjacent(arrow)
    if screen.height() - 60 < 500:
        return  # no room for the taller list on this screen
    panel.start_show_animation(focus=False)
    qtbot.waitUntil(lambda: panel.windowOpacity() >= 0.999, timeout=2000)
    qapp.processEvents()
    assert panel.height() > 420
    assert panel._scroll.verticalScrollBar().maximum() == 0


def test_a_list_above_the_arrow_keeps_its_place_when_it_finishes_opening(qapp, qtbot):
    """QRect.bottom() is one short of the edge; a list above the arrow jumped a pixel."""
    cfg = AppConfig()
    arrow = QLabel("arrow")
    qtbot.addWidget(arrow)
    arrow.resize(60, 40)
    screen = QApplication.primaryScreen().availableGeometry()
    arrow.move(screen.left() + 40, screen.bottom() - 60)  # near the bottom: the list opens above
    arrow.show()
    panel = DropdownPanel(cfg)
    qtbot.addWidget(panel)
    panel.rebuild_buttons([Launcher.new(f"L{i}", "x") for i in range(4)])
    panel.position_adjacent(arrow)
    assert panel._grow_from_top is False
    motion = LockedPairMotion(panel, lambda: 100, hide_duration_ms=100)
    panel.set_locked_pair(motion)
    motion.open([panel], focus_first=False)
    during = panel.geometry()
    qtbot.waitUntil(lambda: not motion.is_running(), timeout=2000)
    assert panel.geometry() == during
    # The list's bottom edge overlaps the arrow's top by the usual 3 px.
    assert panel.y() + panel.height() == arrow.mapToGlobal(QPoint(0, 0)).y() + 3
