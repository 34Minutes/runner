"""Smoke tests for UI widget construction (no full interaction)."""

import pytest
from PySide6.QtWidgets import QApplication

from script_runner.config import Launcher, ConfigManager, AppConfig
from script_runner.ui.add_dialog import AddEditDialog
from script_runner.ui.dropdown import DropdownPanel
from script_runner.ui.launch_button import LaunchButton


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_launch_button_construction(qapp):
    l = Launcher.new("Demo", "echo hi", args="--bar")
    btn = LaunchButton(l)
    assert btn.launcher is l
    assert "Demo" in btn.text()


def test_dropdown_construction(qapp):
    cfg = AppConfig()
    panel = DropdownPanel(cfg)
    assert panel is not None
    # no buttons yet
    panel.rebuild_buttons([])
    assert len(panel._buttons) == 1  # the hint label


def test_add_dialog_advanced_fields_roundtrip(qapp):
    # Create with advanced
    orig = Launcher.new(
        name="AdminTask",
        command="doit",
        working_dir="/tmp/work",
        run_as_admin=True,
        show_console=True,
        enabled=True,
    )
    dlg = AddEditDialog(orig)
    # simulate user didn't change anything, just accept (we bypass exec for test)
    # Manually exercise the accept path by setting result
    # Since we can't easily exec modal in test without qtbot interaction, check load + mutate
    assert dlg._work_dir_edit.text() == "/tmp/work"
    assert dlg._run_as_admin_cb.isChecked() is True
    assert dlg._show_console_cb.isChecked() is True

    # mutate via the widgets as if edited
    dlg._name_edit.setText("AdminTask2")
    dlg._work_dir_edit.setText("/other")
    dlg._run_as_admin_cb.setChecked(False)
    dlg._show_console_cb.setChecked(False)

    # call accept logic directly (private but for test)
    dlg.accept()
    res = dlg.result_launcher
    assert res is not None
    assert res.name == "AdminTask2"
    assert res.working_dir == "/other"
    assert res.run_as_admin is False
    assert res.show_console is False
    # original was mutated too
    assert orig.name == "AdminTask2"


def test_add_dialog_create_new(qapp):
    dlg = AddEditDialog(None)
    dlg._name_edit.setText("NewOne")
    dlg._command_edit.setText("calc")
    dlg._args_edit.setText("--now")
    dlg._work_dir_edit.setText("C:\\temp")
    dlg._run_as_admin_cb.setChecked(True)
    dlg.accept()
    res = dlg.result_launcher
    assert res.name == "NewOne"
    assert res.command == "calc"
    assert res.args == "--now"
    assert res.working_dir == "C:\\temp"
    assert res.run_as_admin is True
