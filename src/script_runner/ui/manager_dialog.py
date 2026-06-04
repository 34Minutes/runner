"""Simple Manage Launchers dialog.

Allows viewing the full list, editing, deleting, and reordering items.
Changes are saved immediately via ConfigManager.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QDialogButtonBox,
    QMessageBox,
)

from ..config import ConfigManager, Launcher
from .add_dialog import AddEditDialog


class ManagerDialog(QDialog):
    """Dialog for managing the list of launchers (edit / delete / reorder)."""

    def __init__(self, cfg: ConfigManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Launchers")
        self.resize(480, 320)
        self._cfg = cfg
        self._launchers: list[Launcher] = list(cfg.config.launchers)  # working copy

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

        # Side buttons
        self._btn_edit = QPushButton("Edit...")
        self._btn_delete = QPushButton("Delete")
        self._btn_up = QPushButton("Move Up")
        self._btn_down = QPushButton("Move Down")
        self._btn_add = QPushButton("Add New...")

        btn_layout = QVBoxLayout()
        btn_layout.addWidget(self._btn_edit)
        btn_layout.addWidget(self._btn_delete)
        btn_layout.addSpacing(12)
        btn_layout.addWidget(self._btn_up)
        btn_layout.addWidget(self._btn_down)
        btn_layout.addStretch()
        btn_layout.addWidget(self._btn_add)

        self._connect_signals()
        self._refresh_list()
        self._rebuild_layout()

    def _rebuild_layout(self):
        # Horizontal: list + buttons
        hbox = QHBoxLayout()
        hbox.addWidget(self._list, 1)

        btns = QVBoxLayout()
        btns.addWidget(self._btn_edit)
        btns.addWidget(self._btn_delete)
        btns.addSpacing(16)
        btns.addWidget(self._btn_up)
        btns.addWidget(self._btn_down)
        btns.addStretch(1)
        btns.addWidget(self._btn_add)
        hbox.addLayout(btns)

        # Vertical wrapper + bottom Close button
        outer = QVBoxLayout(self)
        outer.addLayout(hbox)

        bottom = QHBoxLayout()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        bottom.addStretch()
        bottom.addWidget(buttons)
        outer.addLayout(bottom)

    def _connect_signals(self):
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_up.clicked.connect(self._on_move_up)
        self._btn_down.clicked.connect(self._on_move_down)
        self._btn_add.clicked.connect(self._on_add_new)

        self._list.itemDoubleClicked.connect(self._on_edit)

    def _refresh_list(self):
        self._list.clear()
        for launcher in self._launchers:
            text = launcher.name
            if not launcher.enabled:
                text += "  (disabled)"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, launcher.id)
            item.setToolTip(f"{launcher.command} {launcher.args}".strip())
            self._list.addItem(item)

    def _get_selected_launcher(self) -> Launcher | None:
        item = self._list.currentItem()
        if not item:
            return None
        lid = item.data(Qt.ItemDataRole.UserRole)
        for l in self._launchers:
            if l.id == lid:
                return l
        return None

    def _on_edit(self):
        launcher = self._get_selected_launcher()
        if not launcher:
            return
        dlg = AddEditDialog(launcher, self)
        if dlg.exec():
            # The dialog mutates the launcher in place when editing
            self._cfg.update_launcher(launcher)  # persist
            self._refresh_list()

    def _on_delete(self):
        launcher = self._get_selected_launcher()
        if not launcher:
            return
        reply = QMessageBox.question(
            self,
            "Delete Launcher",
            f"Delete '{launcher.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._launchers = [l for l in self._launchers if l.id != launcher.id]
            self._cfg.remove_launcher(launcher.id)
            self._refresh_list()

    def _on_move_up(self):
        idx = self._list.currentRow()
        if idx <= 0:
            return
        self._launchers[idx], self._launchers[idx-1] = self._launchers[idx-1], self._launchers[idx]
        self._save_order()
        self._refresh_list()
        self._list.setCurrentRow(idx - 1)

    def _on_move_down(self):
        idx = self._list.currentRow()
        if idx < 0 or idx >= len(self._launchers) - 1:
            return
        self._launchers[idx], self._launchers[idx+1] = self._launchers[idx+1], self._launchers[idx]
        self._save_order()
        self._refresh_list()
        self._list.setCurrentRow(idx + 1)

    def _save_order(self):
        ordered_ids = [l.id for l in self._launchers]
        self._cfg.reorder_launchers(ordered_ids)

    def _on_add_new(self):
        dlg = AddEditDialog(None, self)
        if dlg.exec():
            new_l = dlg.result_launcher
            if new_l:
                self._launchers.append(new_l)
                self._cfg.add_launcher(new_l)
                self._refresh_list()
                # select the new one
                self._list.setCurrentRow(self._list.count() - 1)

    def closeEvent(self, event):
        # Ensure any pending order is saved (in case user just reordered without other actions)
        self._save_order()
        super().closeEvent(event)
