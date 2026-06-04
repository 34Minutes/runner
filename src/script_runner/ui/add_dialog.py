"""Dialog for adding or editing a launcher entry.

Fields per spec:
- Name (displayed on button)
- Command / path (separate from parameters)
- Parameters (args)
- Checkbox: Include in the drop-down list (enabled)
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QCheckBox,
    QPushButton,
    QFileDialog,
    QHBoxLayout,
    QWidget,
)

from ..config import Launcher


class AddEditDialog(QDialog):
    """Modal dialog to create or edit a Launcher."""

    def __init__(self, launcher: Launcher | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Launcher" if launcher is None else "Edit Launcher")
        self.setModal(True)
        self.resize(420, 220)

        self._original = launcher
        self._result_launcher: Launcher | None = None

        self._name_edit = QLineEdit()
        self._command_edit = QLineEdit()
        self._args_edit = QLineEdit()
        self._enabled_cb = QCheckBox("Include in dropdown list")
        self._enabled_cb.setChecked(True)

        # Browse button for command
        self._browse_btn = QPushButton("Browse...")
        self._browse_btn.clicked.connect(self._on_browse)

        cmd_row = QWidget()
        cmd_layout = QHBoxLayout(cmd_row)
        cmd_layout.setContentsMargins(0, 0, 0, 0)
        cmd_layout.addWidget(self._command_edit, 1)
        cmd_layout.addWidget(self._browse_btn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        main_layout = QFormLayout()
        main_layout.addRow("Name:", self._name_edit)
        main_layout.addRow("Command / Path:", cmd_row)
        main_layout.addRow("Parameters / Args:", self._args_edit)
        main_layout.addRow("", self._enabled_cb)
        main_layout.addRow(buttons)

        self.setLayout(main_layout)

        if launcher:
            self._name_edit.setText(launcher.name)
            self._command_edit.setText(launcher.command)
            self._args_edit.setText(launcher.args)
            self._enabled_cb.setChecked(launcher.enabled)

        self._name_edit.setFocus()

    def _on_browse(self) -> None:
        # Common filters for executables, scripts, etc.
        filt = "Executables and Scripts (*.exe *.bat *.cmd *.ps1 *.py *.lnk);;All Files (*.*)"
        path, _ = QFileDialog.getOpenFileName(
            self, "Select program or script", "", filt
        )
        if path:
            self._command_edit.setText(path)

    def accept(self) -> None:
        name = self._name_edit.text().strip()
        command = self._command_edit.text().strip()
        if not name or not command:
            # Simple validation
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Missing info", "Name and Command are required.")
            return

        if self._original:
            # Update in place
            self._original.name = name
            self._original.command = command
            self._original.args = self._args_edit.text().strip()
            self._original.enabled = self._enabled_cb.isChecked()
            self._result_launcher = self._original
        else:
            self._result_launcher = Launcher.new(
                name=name,
                command=command,
                args=self._args_edit.text().strip(),
                enabled=self._enabled_cb.isChecked(),
            )

        super().accept()

    @property
    def result_launcher(self) -> Launcher | None:
        return self._result_launcher
