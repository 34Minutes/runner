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
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .stay_on_top import StayOnTopDialog, get_existing_directory, get_open_file_name, warning
from .toggle_switch import ToggleSwitch

from ..config import ConfigManager, Launcher


class _MembershipList(QWidget):
    """Groups this launcher belongs to, with add and remove."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._ids: list[str] = []
        self._names: dict[str, str] = {}

        self._list = QListWidget()
        self._list.setObjectName(title)
        self._list.setMaximumHeight(96)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

        self._combo = QComboBox()
        self._add = QPushButton("Add")
        self._remove = QPushButton("Remove")
        self._add.clicked.connect(self._on_add)
        self._remove.clicked.connect(self._on_remove)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(self._combo, 1)
        controls.addWidget(self._add)
        controls.addWidget(self._remove)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(title))
        layout.addWidget(self._list)
        layout.addLayout(controls)

    def set_groups(self, groups: list[tuple[str, str]], selected_ids: list[str]) -> None:
        """groups is (id, name) in display order. selected_ids are current members."""
        self._names = {group_id: name for group_id, name in groups}
        known = []
        seen: set[str] = set()
        for group_id in selected_ids:
            if group_id in self._names and group_id not in seen:
                known.append(group_id)
                seen.add(group_id)
        self._ids = known
        self._refresh()

    def selected_ids(self) -> list[str]:
        return list(self._ids)

    def _refresh(self) -> None:
        current = self._list.currentRow()
        self._list.clear()
        for group_id in self._ids:
            item = QListWidgetItem(self._names.get(group_id, group_id))
            item.setData(Qt.ItemDataRole.UserRole, group_id)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(min(max(current, 0), self._list.count() - 1))

        chosen = set(self._ids)
        self._combo.clear()
        for group_id, name in self._names.items():
            if group_id not in chosen:
                self._combo.addItem(name, group_id)
        self._add.setEnabled(self._combo.count() > 0)
        self._remove.setEnabled(self._list.count() > 0)

    def _on_add(self) -> None:
        group_id = self._combo.currentData()
        if not group_id or group_id in self._ids:
            return
        self._ids.append(group_id)
        self._refresh()
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == group_id:
                self._list.setCurrentRow(row)
                break

    def _on_remove(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        group_id = item.data(Qt.ItemDataRole.UserRole)
        self._ids = [existing for existing in self._ids if existing != group_id]
        self._refresh()


class AddEditDialog(StayOnTopDialog):
    """Modal dialog to create or edit a Launcher."""

    def __init__(
        self,
        launcher: Launcher | None = None,
        parent: QWidget | None = None,
        cfg: ConfigManager | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Launcher" if launcher is None else "Edit Launcher")
        self.setModal(True)
        self.resize(440, 340)

        self._original = launcher
        self._cfg = cfg
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
        self._only_in_groups_cb = ToggleSwitch("Only In Groups")
        self._only_in_groups_cb.setChecked(False)

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

        self._container_membership = _MembershipList("Container groups I belong to")
        self._execute_membership = _MembershipList("Execute groups I belong to")
        self._load_membership(launcher)

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
        main_layout.addRow("", self._only_in_groups_cb)
        main_layout.addRow("Working directory:", work_row)
        main_layout.addRow("", self._run_as_admin_cb)
        main_layout.addRow("", self._show_console_cb)
        main_layout.addRow(self._container_membership)
        main_layout.addRow(self._execute_membership)
        main_layout.addRow(buttons)

        self.setLayout(main_layout)
        hint = self.sizeHint()
        self.resize(max(520, hint.width() + 24), max(560, hint.height() + 12))

        if launcher:
            self._name_edit.setText(launcher.name)
            self._command_edit.setText(launcher.command)
            self._args_edit.setText(launcher.args)
            self._enabled_cb.setChecked(launcher.enabled)
            self._only_in_groups_cb.setChecked(launcher.only_in_groups)
            self._work_dir_edit.setText(launcher.working_dir or "")
            self._run_as_admin_cb.setChecked(launcher.run_as_admin)
            self._show_console_cb.setChecked(launcher.show_console)

        self._name_edit.setFocus()

    def _load_membership(self, launcher: Launcher | None) -> None:
        cfg = self._cfg
        if cfg is None:
            self._container_membership.set_groups([], [])
            self._execute_membership.set_groups([], [])
            return
        launcher_id = launcher.id if launcher is not None else ""
        containers = [(group.id, group.name) for group in cfg.config.container_groups]
        container_ids = [
            group.id
            for group in cfg.config.container_groups
            if any(member.launcher_id == launcher_id for member in group.members)
        ]
        executes = [(group.id, group.name) for group in cfg.config.groups]
        execute_ids = [
            group.id
            for group in cfg.config.groups
            if any(member.launcher_id == launcher_id for member in group.members)
        ]
        self._container_membership.set_groups(containers, container_ids)
        self._execute_membership.set_groups(executes, execute_ids)

    def _on_browse(self) -> None:
        if sys.platform == "darwin":
            filt = "Applications (*.app);;All Files (*.*)"
        elif sys.platform == "win32":
            filt = "Executables and Scripts (*.exe *.bat *.cmd *.ps1 *.py *.lnk);;All Files (*.*)"
        else:
            filt = "Executables and Scripts (*.app *.py *.sh *.bin);;All Files (*.*)"

        path = get_open_file_name(self, "Select program or script", "", filt)
        if path:
            self._command_edit.setText(path)

    def _on_browse_dir(self) -> None:
        d = get_existing_directory(self, "Select working directory")
        if d:
            self._work_dir_edit.setText(d)

    def accept(self) -> None:
        name = self._name_edit.text().strip()
        command = self._command_edit.text().strip()
        if not name or not command:
            warning(self, "Missing info", "Name and Command are required.")
            return

        work_dir = self._work_dir_edit.text().strip() or None
        run_admin = self._run_as_admin_cb.isChecked()
        show_console = self._show_console_cb.isChecked()

        if self._original:
            self._original.name = name
            self._original.command = command
            self._original.args = self._args_edit.text().strip()
            self._original.enabled = self._enabled_cb.isChecked()
            self._original.only_in_groups = self._only_in_groups_cb.isChecked()
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
                only_in_groups=self._only_in_groups_cb.isChecked(),
                working_dir=work_dir,
                run_as_admin=run_admin,
                show_console=show_console,
            )

        if self._cfg is not None and self._result_launcher is not None:
            self._cfg.set_launcher_membership(
                self._result_launcher.id,
                self._container_membership.selected_ids(),
                self._execute_membership.selected_ids(),
            )

        super().accept()

    @property
    def result_launcher(self) -> Launcher | None:
        return self._result_launcher
