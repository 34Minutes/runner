"""The UI audit: themed dialogs, one button order, the grouped arrow menu,
the launcher screen, the Manage dialogs, and the schedule rows."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QFormLayout, QLabel, QMenu, QPushButton

from runner.config import AppConfig, ConfigManager, Group, GroupMember, Launcher, ScheduleEntry
from runner.ui import theme
from runner.ui.add_dialog import AddEditDialog
from runner.ui.container_dialog import ContainerDialog
from runner.ui.group_dialog import GroupDialog
from runner.ui.group_manager import GroupManagerDialog, ScheduleManagerDialog
from runner.ui.manager_dialog import ManagerDialog
from runner.ui.schedule_editor import ScheduleEditor
from runner.ui.trigger import ArrowContextMenu, ArrowSubmenu, TriggerWidget


@pytest.fixture
def cfg(monkeypatch, tmp_path):
    monkeypatch.setattr("runner.config.platformdirs.user_config_dir", lambda *a, **k: str(tmp_path))
    manager = ConfigManager()
    for name in ("Alpha", "Beta", "Gamma"):
        manager.add_launcher(Launcher.new(name, name.lower()))
    return manager


@pytest.fixture(autouse=True)
def _dark_after():
    yield
    theme.use("dark")


# ------------------------------------------------------------ 1. theming


@pytest.mark.parametrize("scheme_id", ["dark", "medium", "bright"])
def test_dialogs_take_the_schemes_colours(qapp, qtbot, cfg, scheme_id):
    scheme = theme.use(scheme_id)
    colors = theme.dialog_colors(scheme)
    for dialog in (AddEditDialog(None, None, cfg), GroupDialog(cfg), ManagerDialog(cfg)):
        qtbot.addWidget(dialog)
        assert f"background: {colors.window}" in dialog.styleSheet()
        assert dialog.palette().color(dialog.palette().ColorRole.Window).name() == colors.window
        assert dialog.palette().color(dialog.palette().ColorRole.Text).name() == colors.text


def test_each_scheme_has_its_own_dialog_colours():
    windows = {theme.dialog_colors(scheme).window for scheme in theme.SCHEMES}
    assert len(windows) == 3


def test_disabled_reads_dimmer_than_text_in_every_scheme():
    def distance(a, b):
        return sum(abs(x - y) for x, y in zip(theme._channels(a), theme._channels(b), strict=True))

    for scheme in theme.SCHEMES:
        colors = theme.dialog_colors(scheme)
        assert distance(colors.disabled, colors.window) < distance(colors.text, colors.window) * 0.6


def test_solid_and_mix():
    assert theme.solid("rgba(35, 35, 38, 245)") == "#232326"
    assert theme.solid("#eee") == "#eeeeee"
    assert theme.mix("#000000", "#ffffff", 0.5) == "#808080"


def test_check_icon_is_written_once(tmp_path, monkeypatch):
    import stat
    from pathlib import Path

    monkeypatch.setattr(theme.tempfile, "gettempdir", lambda: str(tmp_path))
    path = theme.check_icon("#ffffff")
    assert path.endswith(".png")
    data = Path(path).read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    if sys.platform != "win32":
        assert stat.S_IMODE(Path(path).parent.stat().st_mode) == 0o700
    assert theme.check_icon("#ffffff") == path


def test_dialog_qss_preserves_keyboard_focus_rings():
    qss = theme.dialog_qss()
    assert "outline: none" not in qss
    assert "QPushButton:focus" in qss
    assert "QListWidget:focus" in qss


def test_custom_widgets_have_accessible_names(qapp, qtbot):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    from runner.ui.date_dial import MetalDial
    from runner.ui.dropdown import DropdownPanel
    from runner.ui.interval_roller import IntervalRoller
    from runner.ui.toggle_switch import ToggleSwitch

    trigger = TriggerWidget(AppConfig())
    dial = MetalDial()
    roller = IntervalRoller()
    switch = ToggleSwitch("Pin open")
    panel = DropdownPanel(AppConfig())
    for widget in (trigger, dial, roller, switch, panel):
        qtbot.addWidget(widget)
        assert widget.accessibleName()

    # Container rows are keyboard-navigable and open on Right or Enter.
    panel.set_submenu_items([("c1", "Tools")])
    panel.rebuild_buttons([Launcher.new("Alpha", "alpha")])
    panel.show()
    opened = []
    panel.submenu_hovered.connect(opened.append)
    panel.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier))
    panel.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier))
    assert opened == ["c1"]


# ------------------------------------------------- 2. one button order


def _visible_buttons(dialog):
    dialog.show()
    return [button.text() for button in dialog.findChildren(QPushButton) if button.isVisible()]


def test_cancel_comes_before_save_on_every_editing_dialog(qapp, qtbot, cfg):
    for dialog in (GroupDialog(cfg), ContainerDialog(cfg)):
        qtbot.addWidget(dialog)
        texts = _visible_buttons(dialog)
        assert texts.index("Cancel") < texts.index("Save")
        dialog.close()
    add = AddEditDialog(None, None, cfg)
    qtbot.addWidget(add)
    add.show()
    buttons = sorted(
        (b for b in add.findChildren(QPushButton) if b.text() in ("Cancel", "Save")),
        key=lambda b: b.mapToGlobal(QPoint(0, 0)).x(),
    )
    assert [b.text() for b in buttons] == ["Cancel", "Save"]
    add.close()


# --------------------------------------------------- 3. the arrow menu


def _arrow_menu(trigger):
    found = [m for m in trigger.findChildren(QMenu) if any(a.text() == "Exit" for a in m.actions())]
    assert found
    return found[-1]


def test_dialog_rows_end_in_an_ellipsis_and_use_title_case(qapp, qtbot):
    trigger = TriggerWidget(AppConfig())
    qtbot.addWidget(trigger)
    trigger._show_context_menu(QPoint(8, 8))
    menu = _arrow_menu(trigger)
    qtbot.addWidget(menu)
    rows = [a.text() for a in menu.actions() if a.text() and not a.menu()]
    for submenu in (a.menu() for a in menu.actions() if a.menu() is not None):
        rows += [a.text() for a in submenu.actions() if a.text()]
    opening = [text for text in rows if text.startswith(("Add ", "Manage "))]
    assert opening and all(text.endswith("…") for text in opening)
    assert not any(text.endswith("...") for text in rows)
    menu.close()


def test_choosing_a_submenu_row_counts_as_a_choice(qapp, qtbot):
    parent = ArrowContextMenu()
    qtbot.addWidget(parent)
    submenu = ArrowSubmenu("Schedules", parent)
    action = submenu.addAction("Add Schedule…")
    assert parent._chose_action is False
    submenu._mark_parent_chosen(action)
    assert parent._chose_action is True


# ---------------------------------------------- 4. the launcher screen


def test_launcher_fields_take_the_dialogs_width(qapp, qtbot, cfg):
    dialog = AddEditDialog(None, None, cfg)
    qtbot.addWidget(dialog)
    form = dialog.findChild(QFormLayout)
    assert form.fieldGrowthPolicy() == QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
    dialog.show()
    assert dialog._args_edit.width() > dialog.width() * 0.5


@pytest.mark.skipif(sys.platform == "win32", reason="the Windows switches show on Windows")
def test_windows_only_switches_are_hidden_elsewhere(qapp, qtbot, cfg):
    dialog = AddEditDialog(None, None, cfg)
    qtbot.addWidget(dialog)
    dialog.show()
    assert dialog._run_as_admin_cb.isVisible() is False
    assert dialog._show_console_cb.isVisible() is False
    assert dialog._enabled_cb.isVisible() is True


def test_membership_lists_tick_and_say_when_empty(qapp, qtbot, cfg):
    alpha = cfg.config.launchers[0]
    plain = Group.new("Plain", [GroupMember(alpha.id)])
    timed = Group.new("Timed")
    timed.scheduled = True
    cfg.add_group(plain)
    cfg.add_group(timed)
    dialog = AddEditDialog(alpha, None, cfg)
    qtbot.addWidget(dialog)
    dialog.show()
    executes = dialog._execute_membership._list
    assert [executes.item(row).text() for row in range(executes.count())] == ["Plain", "Timed  (schedule)"]
    assert dialog._execute_membership.selected_ids() == [plain.id]
    # No container groups: a line says so instead of an empty box.
    assert dialog._container_membership._list.isVisible() is False
    assert dialog._container_membership._empty.isVisible() is True
    assert "No container groups yet" in dialog._container_membership._empty.text()


# ------------------------------------------------ 5. the Manage dialogs


@pytest.mark.parametrize("make", [ManagerDialog, GroupManagerDialog])
def test_row_buttons_wait_for_a_selection(qapp, qtbot, cfg, make):
    cfg.add_group(Group.new("One"))
    cfg.add_group(Group.new("Two"))
    dialog = make(cfg)
    qtbot.addWidget(dialog)
    assert not any(b.isEnabled() for b in (dialog._btn_edit, dialog._btn_delete, dialog._btn_up, dialog._btn_down))
    assert dialog._btn_add.isEnabled()
    assert not dialog._btn_edit.isDefault() and not dialog._btn_edit.autoDefault()

    dialog._list.setCurrentRow(0)
    assert dialog._btn_edit.isEnabled() and dialog._btn_delete.isEnabled()
    assert dialog._btn_up.isEnabled() is False
    assert dialog._btn_down.isEnabled() is True

    dialog._list.setCurrentRow(dialog._list.count() - 1)
    assert dialog._btn_up.isEnabled() is True
    assert dialog._btn_down.isEnabled() is False


def test_an_empty_manage_list_says_so(qapp, qtbot, cfg):
    dialog = ScheduleManagerDialog(cfg)
    qtbot.addWidget(dialog)
    assert dialog._list.count() == 0
    assert dialog._list.empty_text.startswith("No schedules yet")
    dialog.show()
    dialog._list.repaint()


# ------------------------------------------------ 6. the schedule rows


def test_every_schedule_row_keeps_room_for_the_next_tag(qapp, qtbot):
    now = datetime(2026, 11, 23, 9, 0)
    entries = [ScheduleEntry.new(now + timedelta(hours=hours)) for hours in (1, 5, 9)]
    editor = ScheduleEditor(entries, now=lambda: now)
    qtbot.addWidget(editor)
    editor.resize(700, 300)
    editor.show()
    tags = [label for label in editor.findChildren(QLabel) if label.objectName() == "scheduleNext"]
    assert len(tags) == 3
    assert [tag.text() for tag in tags].count("next") == 1
    dates = [b for b in editor.findChildren(QPushButton) if b.objectName() == "scheduleDate"]
    assert len({button.width() for button in dates}) == 1


def test_member_columns_explain_themselves(qapp, qtbot, cfg):
    dialog = GroupDialog(cfg)
    qtbot.addWidget(dialog)
    tips = [dialog._table.horizontalHeaderItem(column).toolTip() for column in range(3)]
    assert all(tips)
    alpha = cfg.config.launchers[0]
    assert dialog.concurrent_checkbox(alpha.id).toolTip()
    assert dialog.only_in_groups_checkbox(alpha.id).toolTip()
