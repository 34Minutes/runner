"""Keep dialogs above the always-on-top arrow.

The arrow uses WindowStaysOnTopHint. On Windows an owned dialog without that
flag is not topmost, so it opens behind the arrow.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox, QWidget


def mark_stay_on_top(widget: QWidget) -> None:
    widget.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)


class StayOnTopDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        mark_stay_on_top(self)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.raise_()
        self.activateWindow()


def warning(parent: QWidget | None, title: str, text: str) -> None:
    box = QMessageBox(
        QMessageBox.Icon.Warning,
        title,
        text,
        QMessageBox.StandardButton.Ok,
        parent,
    )
    mark_stay_on_top(box)
    box.exec()


def question(
    parent: QWidget | None,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton,
) -> QMessageBox.StandardButton:
    box = QMessageBox(QMessageBox.Icon.Question, title, text, buttons, parent)
    mark_stay_on_top(box)
    return QMessageBox.StandardButton(box.exec())


def get_open_file_name(parent: QWidget, title: str, directory: str, name_filter: str) -> str:
    dlg = QFileDialog(parent, title, directory, name_filter)
    dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
    mark_stay_on_top(dlg)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return ""
    files = dlg.selectedFiles()
    return files[0] if files else ""


def get_existing_directory(parent: QWidget, title: str) -> str:
    dlg = QFileDialog(parent, title)
    dlg.setFileMode(QFileDialog.FileMode.Directory)
    dlg.setOption(QFileDialog.Option.ShowDirsOnly, True)
    mark_stay_on_top(dlg)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return ""
    files = dlg.selectedFiles()
    return files[0] if files else ""
