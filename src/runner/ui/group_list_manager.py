"""Manage execute groups or container groups: edit, delete, and reorder.

Same job as Manage Launchers. GroupManagerDialog and ContainerManagerDialog
only say which list they manage and which dialog edits one entry.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QHBoxLayout,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..config import ConfigManager
from .manage_list import ManageList, keep_buttons_in_step
from .stay_on_top import StayOnTopDialog, question


class GroupListManagerDialog(StayOnTopDialog):
    """Edit, delete, and reorder one kind of group."""

    # Set by each subclass.
    TITLE = "Manage Groups"
    DELETE_TITLE = "Delete Group"
    EMPTY_TEXT = "Nothing here yet. Press Add New… to make one."

    def __init__(self, cfg: ConfigManager, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.TITLE)
        self.resize(480, 320)
        self._cfg = cfg
        self._groups = list(self._saved())

        self._list = ManageList(self.EMPTY_TEXT)

        self._btn_edit = QPushButton("Edit…")
        self._btn_delete = QPushButton("Delete")
        self._btn_up = QPushButton("Move Up")
        self._btn_down = QPushButton("Move Down")
        self._btn_add = QPushButton("Add New…")

        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_up.clicked.connect(self._on_move_up)
        self._btn_down.clicked.connect(self._on_move_down)
        self._btn_add.clicked.connect(self._on_add)
        self._list.itemDoubleClicked.connect(self._on_edit)

        hbox = QHBoxLayout()
        hbox.addWidget(self._list, 1)
        buttons = QVBoxLayout()
        buttons.addWidget(self._btn_edit)
        buttons.addWidget(self._btn_delete)
        buttons.addSpacing(16)
        buttons.addWidget(self._btn_up)
        buttons.addWidget(self._btn_down)
        buttons.addStretch(1)
        buttons.addWidget(self._btn_add)
        hbox.addLayout(buttons)

        outer = QVBoxLayout(self)
        outer.addLayout(hbox)
        bottom = QHBoxLayout()
        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.accept)
        bottom.addStretch()
        bottom.addWidget(close_box)
        outer.addLayout(bottom)

        self._refresh_list()
        keep_buttons_in_step(self._list, self._btn_edit, self._btn_delete, self._btn_up, self._btn_down, self._btn_add)

    # ---------------------------------------------------- subclass hooks

    def _saved(self) -> list:
        """The groups as stored in the config, in order."""
        raise NotImplementedError

    def _editor(self, group):
        """The add/edit dialog for one group. group is None for Add."""
        raise NotImplementedError

    def _store_new(self, group) -> None:
        raise NotImplementedError

    def _store_edit(self, group) -> None:
        raise NotImplementedError

    def _remove(self, group_id: str) -> None:
        raise NotImplementedError

    def _reorder(self, ordered_ids: list[str]) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------- list

    def _refresh_list(self) -> None:
        self._list.clear()
        for group in self._groups:
            count = len(group.members)
            noun = "launcher" if count == 1 else "launchers"
            item = QListWidgetItem(f"{group.name}  ({count} {noun})")
            item.setData(Qt.ItemDataRole.UserRole, group.id)
            self._list.addItem(item)

    def _selected_group(self):
        item = self._list.currentItem()
        if item is None:
            return None
        group_id = item.data(Qt.ItemDataRole.UserRole)
        return next((group for group in self._groups if group.id == group_id), None)

    def _on_edit(self) -> None:
        group = self._selected_group()
        if group is None:
            return
        dialog = self._editor(group)
        if dialog.exec() and dialog.result_group is not None:
            self._store_edit(dialog.result_group)
            self._groups = list(self._saved())
            self._refresh_list()

    def _on_delete(self) -> None:
        group = self._selected_group()
        if group is None:
            return
        reply = question(
            self,
            self.DELETE_TITLE,
            f"Delete '{group.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._groups = [item for item in self._groups if item.id != group.id]
        self._remove(group.id)
        self._refresh_list()

    def _on_move_up(self) -> None:
        index = self._list.currentRow()
        if index <= 0:
            return
        self._groups[index], self._groups[index - 1] = self._groups[index - 1], self._groups[index]
        self._save_order()
        self._refresh_list()
        self._list.setCurrentRow(index - 1)

    def _on_move_down(self) -> None:
        index = self._list.currentRow()
        if index < 0 or index >= len(self._groups) - 1:
            return
        self._groups[index], self._groups[index + 1] = self._groups[index + 1], self._groups[index]
        self._save_order()
        self._refresh_list()
        self._list.setCurrentRow(index + 1)

    def _save_order(self) -> None:
        self._reorder([group.id for group in self._groups])

    def _on_add(self) -> None:
        dialog = self._editor(None)
        if dialog.exec() and dialog.result_group is not None:
            self._store_new(dialog.result_group)
            self._groups = list(self._saved())
            self._refresh_list()
            self._list.setCurrentRow(self._list.count() - 1)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._save_order()
        super().closeEvent(event)
