"""Dialog for adding or editing a launcher entry.

Fields:
- Name, Command/Path (+Browse), Parameters/Args, Include in list (enabled)
- Working directory (+Browse dir)
- Run as administrator, Show console window (shown on Windows only)
- Which container groups and execute groups it is in, as tick lists
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .stay_on_top import StayOnTopDialog, get_existing_directory, get_open_file_name, warning
from .toggle_switch import ToggleSwitch

from ..config import ConfigManager, Launcher

DUPLICATE_TIP = "Save this launcher, then add a numbered copy of it and edit the copy."


class _MembershipList(QWidget):
    """The groups of one kind, each with a tick for whether this launcher is in it."""

    ROW_HEIGHT = 26
    MAX_ROWS = 5

    def __init__(self, title: str, empty_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._list = QListWidget()
        self._list.setObjectName(title)
        self._list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.itemClicked.connect(self._toggle)
        self._empty = QLabel(empty_text)
        self._empty.setObjectName("membershipEmpty")
        self._empty.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(QLabel(title))
        layout.addWidget(self._list)
        layout.addWidget(self._empty)

    def set_groups(self, groups: list[tuple[str, str]], selected_ids: list[str]) -> None:
        """groups is (id, name) in display order. selected_ids are current members."""
        chosen = set(selected_ids)
        self._list.clear()
        for group_id, name in groups:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, group_id)
            # Not user-checkable: the view would flip the box and then report
            # the click as well. _toggle handles every click on the row once.
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(Qt.CheckState.Checked if group_id in chosen else Qt.CheckState.Unchecked)
            item.setSizeHint(QSize(0, self.ROW_HEIGHT))
            self._list.addItem(item)
        rows = min(max(len(groups), 1), self.MAX_ROWS)
        self._list.setFixedHeight(rows * self.ROW_HEIGHT + 6)
        self._list.setVisible(bool(groups))
        self._empty.setVisible(not groups)

    def selected_ids(self) -> list[str]:
        return [
            self._list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self._list.count())
            if self._list.item(row).checkState() == Qt.CheckState.Checked
        ]

    def set_checked(self, group_id: str, checked: bool) -> None:
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == group_id:
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def _toggle(self, item: QListWidgetItem) -> None:
        """A click anywhere on the row, box or name, ticks or unticks it."""
        checked = item.checkState() == Qt.CheckState.Checked
        item.setCheckState(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)


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

        # Browse button for command
        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.clicked.connect(self._on_browse)

        cmd_row = QWidget()
        cmd_layout = QHBoxLayout(cmd_row)
        cmd_layout.setContentsMargins(0, 0, 0, 0)
        cmd_layout.addWidget(self._command_edit, 1)
        cmd_layout.addWidget(self._browse_btn)

        self._work_dir_edit = QLineEdit()
        self._work_dir_edit.setPlaceholderText("Optional: run with this working directory")
        self._browse_dir_btn = QPushButton("Browse…")
        self._browse_dir_btn.clicked.connect(self._on_browse_dir)

        work_row = QWidget()
        work_layout = QHBoxLayout(work_row)
        work_layout.setContentsMargins(0, 0, 0, 0)
        work_layout.addWidget(self._work_dir_edit, 1)
        work_layout.addWidget(self._browse_dir_btn)

        # Saved on every platform, but they only do anything on Windows.
        self._run_as_admin_cb = ToggleSwitch("Run as administrator")
        self._show_console_cb = ToggleSwitch("Show console window")

        self._container_membership = _MembershipList(
            "Member of container groups", "No container groups yet."
        )
        self._execute_membership = _MembershipList(
            "Member of execute groups and schedules", "No execute groups or schedules yet."
        )
        self._load_membership(launcher)

        # Laid out by hand, not with QDialogButtonBox: that follows each
        # platform's order, which puts Save first on Windows and Linux. Every
        # Runner dialog has Cancel then Save.
        save_button = QPushButton("Save")
        save_button.setDefault(True)
        save_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.setAutoDefault(False)
        cancel_button.clicked.connect(self.reject)
        # Saves this launcher, then a numbered copy, and carries on editing the copy.
        self.duplicate_button = QPushButton("Duplicate")
        self.duplicate_button.setAutoDefault(False)
        self.duplicate_button.setToolTip(DUPLICATE_TIP)
        self.duplicate_button.clicked.connect(self.duplicate)
        self.duplicate_button.setVisible(cfg is not None)
        buttons = QHBoxLayout()
        buttons.addWidget(self.duplicate_button)
        buttons.addStretch(1)
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)
        for button in (self._browse_btn, self._browse_dir_btn):
            button.setAutoDefault(False)

        form = QFormLayout()
        # macOS keeps fields at their natural width by default, which cut the
        # hints short. Let them take the dialog's width.
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.addRow("Name:", self._name_edit)
        form.addRow("Command / Path:", cmd_row)
        form.addRow("Parameters / Args:", self._args_edit)
        form.addRow("Working directory:", work_row)

        toggles = QVBoxLayout()
        toggles.setSpacing(8)
        toggles.addWidget(self._enabled_cb)
        if sys.platform == "win32":
            toggles.addWidget(self._run_as_admin_cb)
            toggles.addWidget(self._show_console_cb)
        else:
            self._run_as_admin_cb.hide()
            self._show_console_cb.hide()
        form.addRow("", toggles)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(form)
        main_layout.addSpacing(8)
        main_layout.addWidget(self._container_membership)
        main_layout.addSpacing(4)
        main_layout.addWidget(self._execute_membership)
        main_layout.addStretch(1)
        main_layout.addLayout(buttons)

        for field in (self._name_edit, self._command_edit, self._args_edit, self._work_dir_edit):
            field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._name_edit.setPlaceholderText("What the list shows, e.g. Brave")
        hint = self.sizeHint()
        self.resize(max(560, hint.width() + 24), hint.height() + 12)

        # Ids this screen saved itself, by duplicating. The caller saves the last one.
        self.saved_ids: list[str] = []

        if launcher:
            self._show(launcher)

        self._name_edit.setFocus()

    def _show(self, launcher: Launcher) -> None:
        self._name_edit.setText(launcher.name)
        self._command_edit.setText(launcher.command)
        self._args_edit.setText(launcher.args)
        self._enabled_cb.setChecked(self._included_in_dropdown(launcher))
        self._work_dir_edit.setText(launcher.working_dir or "")
        self._run_as_admin_cb.setChecked(launcher.run_as_admin)
        self._show_console_cb.setChecked(launcher.show_console)

    def _included_in_dropdown(self, launcher: Launcher) -> bool:
        return launcher.show_in_main

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
        executes = [
            (group.id, f"{group.name}  (schedule)" if group.scheduled else group.name)
            for group in cfg.config.groups
        ]
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

    def duplicate(self) -> None:
        """Save what is on screen, then make a numbered copy and edit that.

        The copy is saved straight away, so it stays even if this screen is
        then cancelled. Cancel only drops changes made to the copy.
        """
        if self._cfg is None or not self._apply():
            return
        saved = self._result_launcher
        assert saved is not None
        if self._original is None:
            self._cfg.add_launcher(saved)
        else:
            self._cfg.update_launcher(saved)
        copy = self._cfg.duplicate_launcher(saved.id)
        if copy is None:
            return
        self.saved_ids.append(saved.id)
        self._original = copy
        self._result_launcher = copy
        self.setWindowTitle("Edit Launcher")
        self._show(copy)
        # The tick lists already show the original's groups, which the copy is now in.
        self._name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        self._name_edit.selectAll()

    def accept(self) -> None:
        if self._apply():
            super().accept()

    def _apply(self) -> bool:
        """Check the fields and write them to the launcher. False when one is missing."""
        name = self._name_edit.text().strip()
        command = self._command_edit.text().strip()
        if not name or not command:
            warning(self, "Missing info", "Name and Command are required.")
            return False

        work_dir = self._work_dir_edit.text().strip() or None
        run_admin = self._run_as_admin_cb.isChecked()
        show_console = self._show_console_cb.isChecked()
        included = self._enabled_cb.isChecked()

        if self._original:
            self._original.name = name
            self._original.command = command
            self._original.args = self._args_edit.text().strip()
            self._original.working_dir = work_dir
            self._original.run_as_admin = run_admin
            self._original.show_console = show_console
            self._result_launcher = self._original
        else:
            self._result_launcher = Launcher.new(
                name=name,
                command=command,
                args=self._args_edit.text().strip(),
                working_dir=work_dir,
                run_as_admin=run_admin,
                show_console=show_console,
            )

        if self._result_launcher is not None:
            self._result_launcher.show_in_main = included

        if self._cfg is not None and self._result_launcher is not None:
            self._cfg.set_launcher_membership(
                self._result_launcher.id,
                self._container_membership.selected_ids(),
                self._execute_membership.selected_ids(),
            )
        return True

    @property
    def result_launcher(self) -> Launcher | None:
        return self._result_launcher
