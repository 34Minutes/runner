"""The list and side buttons shared by every Manage dialog.

ManageList says so when it is empty instead of showing a blank box.
keep_buttons_in_step enables Edit, Delete, and Move only when a row is
selected and the move has somewhere to go, and stops any of them from
looking like the default button: Enter on an empty selection would do
nothing.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import QListWidget, QPushButton


class ManageList(QListWidget):
    def __init__(self, empty_text: str, parent=None) -> None:
        super().__init__(parent)
        self._empty_text = empty_text
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

    @property
    def empty_text(self) -> str:
        return self._empty_text

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        if self.count():
            return
        painter = QPainter(self.viewport())
        try:
            painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
            area = self.viewport().rect().adjusted(16, 16, -16, -16)
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self._empty_text)
        finally:
            painter.end()


def keep_buttons_in_step(
    listing: QListWidget,
    edit: QPushButton,
    delete: QPushButton,
    up: QPushButton,
    down: QPushButton,
    *others: QPushButton,
) -> None:
    for button in (edit, delete, up, down, *others):
        button.setAutoDefault(False)
        button.setDefault(False)

    def update() -> None:
        # The model empties itself while the dialog is torn down, after the
        # list's Python side is gone. Nothing is left to update then.
        try:
            row = listing.currentRow()
            chosen = row >= 0 and listing.currentItem() is not None and listing.currentItem().isSelected()
            count = listing.count()
        except RuntimeError:
            return
        edit.setEnabled(chosen)
        delete.setEnabled(chosen)
        up.setEnabled(chosen and row > 0)
        down.setEnabled(chosen and row < count - 1)

    listing.currentRowChanged.connect(lambda _row: update())
    listing.itemSelectionChanged.connect(update)
    model = listing.model()
    model.rowsInserted.connect(lambda *_: update())
    model.rowsRemoved.connect(lambda *_: update())
    model.modelReset.connect(update)
    update()
