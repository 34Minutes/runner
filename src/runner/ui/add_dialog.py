"""Dialog for adding or editing a launcher entry.

Fields:
- Name, Command/Path (+Browse), Parameters/Args, Include in list (enabled)
- Working directory (+Browse dir)
- Run as administrator (Windows), Show console (Windows)
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QHBoxLayout,
    QWidget,
)

from .toggle_switch import ToggleSwitch

from ..config import Launcher


class AddEditDialog(QDialog):
    """Modal dialog to create or edit a Launcher."""

    def __init__(self, launcher: Launcher | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Launcher" if launcher is None else "Edit Launcher")
        self.setModal(True)
        self.resize(440, 340)

        self._original = launcher
        self._result_launcher: Launcher | None = None

        self._name_edit = QLineEdit()
        self._command_edit = QLineEdit()
        if sys.platform == "darwin":
            self._command_edit.setPlaceholderText('e.g. /Applications/Brave Browser.app  or  Brave Browser')
        elif sys.platform == "win32":
            self._command_edit.setPlaceholderText('e.g. brave  or  C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe')
        else:
            self._command_edit.setPlaceholderText('e.g. brave  or  /usr/bin/brave')
        self._args_edit = QLineEdit()
        self._args_edit.setPlaceholderText('e.g. https://x.com  or  --new-window')
        self._enabled_cb = ToggleSwitch("Include in dropdown list")
        self._enabled_cb.setChecked(True)

        # Browse button for command
        self._browse_btn = QPushButton("Browse...")
        self._browse_btn.clicked.connect(self._on_browse)

        cmd_row = QWidget()
        cmd_layout = QHBoxLayout(cmd_row)
        cmd_layout.setContentsMargins(0, 0, 0, 0)
        cmd_layout.addWidget(self._command_edit, 1)
        cmd_layout.addWidget(self._browse_btn)

        self._work_dir_edit = QLineEdit()
        self._work_dir_edit.setPlaceholderText("Optional: run with this working directory")
        self._browse_dir_btn = QPushButton("Browse...")
        self._browse_dir_btn.clicked.connect(self._on_browse_dir)

        work_row = QWidget()
        work_layout = QHBoxLayout(work_row)
        work_layout.setContentsMargins(0, 0, 0, 0)
        work_layout.addWidget(self._work_dir_edit, 1)
        work_layout.addWidget(self._browse_dir_btn)

        self._run_as_admin_cb = ToggleSwitch("Run as administrator (Windows)")
        self._show_console_cb = ToggleSwitch("Show console / terminal (Windows)")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("Save")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        main_layout = QFormLayout()
        main_layout.addRow("Name:", self._name_edit)
        main_layout.addRow("Command / Path:", cmd_row)
        main_layout.addRow("Parameters / Args:", self._args_edit)
        main_layout.addRow("", self._enabled_cb)
        main_layout.addRow("Working directory:", work_row)
        main_layout.addRow("", self._run_as_admin_cb)
        main_layout.addRow("", self._show_console_cb)
        main_layout.addRow(buttons)

        self.setLayout(main_layout)

        if launcher:
            self._name_edit.setText(launcher.name)
            self._command_edit.setText(launcher.command)
            self._args_edit.setText(launcher.args)
            self._enabled_cb.setChecked(launcher.enabled)
            self._work_dir_edit.setText(launcher.working_dir or "")
            self._run_as_admin_cb.setChecked(launcher.run_as_admin)
            self._show_console_cb.setChecked(launcher.show_console)

        self._name_edit.setFocus()

    def _on_browse(self) -> None:
        if sys.platform == "darwin":
            filt = "Applications (*.app);;All Files (*.*)"
        elif sys.platform == "win32":
            filt = "Executables and Scripts (*.exe *.bat *.cmd *.ps1 *.py *.lnk);;All Files (*.*)"
        else:
            filt = "Executables and Scripts (*.app *.py *.sh *.bin);;All Files (*.*)"

        path, _ = QFileDialog.getOpenFileName(
            self, "Select program or script", "", filt
        )
        if path:
            self._command_edit.setText(path)

    def _on_browse_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Select working directory")
        if d:
            self._work_dir_edit.setText(d)

    def accept(self) -> None:
        name = self._name_edit.text().strip()
        command = self._command_edit.text().strip()
        if not name or not command:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Missing info", "Name and Command are required.")
            return

        work_dir = self._work_dir_edit.text().strip() or None
        run_admin = self._run_as_admin_cb.isChecked()
        show_console = self._show_console_cb.isChecked()

        if self._original:
            self._original.name = name
            self._original.command = command
            self._original.args = self._args_edit.text().strip()
            self._original.enabled = self._enabled_cb.isChecked()
            self._original.working_dir = work_dir
            self._original.run_as_admin = run_admin
            self._original.show_console = show_console
            self._result_launcher = self._original
        else:
            self._result_launcher = Launcher.new(
                name=name,
                command=command,
                args=self._args_edit.text().strip(),
                enabled=self._enabled_cb.isChecked(),
                working_dir=work_dir,
                run_as_admin=run_admin,
                show_console=show_console,
            )

        super().accept()

    @property
    def result_launcher(self) -> Launcher | None:
        return self._result_launcher
