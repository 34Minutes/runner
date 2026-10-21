"""Keep dialogs above the always-on-top arrow.

The arrow uses WindowStaysOnTopHint. On Windows an owned dialog without that
flag is not topmost, so it opens behind the arrow.

On macOS that same flag makes Qt skip the native open panel and use its own
file dialog. The widget dialog treats an .app bundle as a folder, so choosing
Notes.app walks into the bundle. The macOS open dialog accepts the bundle as
the selected program instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QFileDialog, QLineEdit, QMessageBox, QWidget


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


def _is_selectable_app_bundle(path: str) -> bool:
    """True when path is a macOS application bundle the user means to launch."""
    if sys.platform != "darwin" or not path:
        return False
    cleaned = path.rstrip("/")
    if not Path(cleaned).name.casefold().endswith(".app"):
        return False
    return Path(cleaned).is_dir()


class _BundleSelectingFileDialog(QFileDialog):
    """Widget file dialog that selects an .app bundle instead of entering it."""

    def __init__(self, parent: QWidget | None, title: str, directory: str, name_filter: str) -> None:
        super().__init__(parent, title, directory, name_filter)
        self._bundle_choice = ""
        self.directoryEntered.connect(self._select_bundle_instead_of_entering)
        self.currentChanged.connect(self._show_bundle_name)
        # A Python subclass is not the native dialog, and Qt only builds the
        # file widgets when native show() fails. Force them into existence.
        self.setOption(QFileDialog.Option.DontUseNativeDialog, True)

    def _show_bundle_name(self, path: str) -> None:
        # ExistingFile mode omits directories from the name field. A bundle is
        # a directory, so highlighting Notes.app would leave that field blank.
        if self._bundle_choice or not _is_selectable_app_bundle(path):
            return
        edit = self.findChild(QLineEdit, "fileNameEdit")
        if edit is None or edit.hasFocus():
            return
        name = Path(path.rstrip("/")).name
        if edit.text() == name:
            return
        edit.blockSignals(True)
        edit.setText(name)
        edit.blockSignals(False)

    def _select_bundle_instead_of_entering(self, directory: str) -> None:
        # Double-click and keyboard activation call setDirectory before this
        # signal. Accept on the next turn so the click handler can finish.
        if self._bundle_choice or not _is_selectable_app_bundle(directory):
            return
        self._bundle_choice = directory.rstrip("/")
        parent = str(Path(self._bundle_choice).parent)
        self.setDirectory(parent)
        QTimer.singleShot(0, self._finish_bundle_choice)

    def _finish_bundle_choice(self) -> None:
        if not self._bundle_choice or self.result() == QDialog.DialogCode.Accepted:
            return
        if not self.isVisible():
            return
        QDialog.accept(self)

    def selectedFiles(self) -> list[str]:  # type: ignore[override]
        if self._bundle_choice:
            return [self._bundle_choice]
        return super().selectedFiles()

    def accept(self) -> None:
        if self._bundle_choice:
            QDialog.accept(self)
            return
        paths = super().selectedFiles()
        if len(paths) == 1 and _is_selectable_app_bundle(paths[0]):
            self._bundle_choice = paths[0].rstrip("/")
            QDialog.accept(self)
            return
        super().accept()


def _open_file_dialog(parent: QWidget, title: str, directory: str, name_filter: str) -> QFileDialog:
    if sys.platform == "darwin":
        dlg: QFileDialog = _BundleSelectingFileDialog(parent, title, directory, name_filter)
    else:
        dlg = QFileDialog(parent, title, directory, name_filter)
    dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
    mark_stay_on_top(dlg)
    return dlg


def get_open_file_name(parent: QWidget, title: str, directory: str, name_filter: str) -> str:
    dlg = _open_file_dialog(parent, title, directory, name_filter)
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
