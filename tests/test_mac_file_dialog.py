"""macOS browse dialog must select an .app bundle instead of entering it."""

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFileSystemModel, QLineEdit, QListView

from runner.ui.stay_on_top import (
    _BundleSelectingFileDialog,
    _is_selectable_app_bundle,
    _open_file_dialog,
)


def test_open_file_dialog_stays_above_the_arrow(qapp):
    dlg = _open_file_dialog(None, "Select program or script", "", "Applications (*.app)")
    assert dlg.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert dlg.fileMode() == dlg.FileMode.ExistingFile
    if sys.platform == "darwin":
        assert isinstance(dlg, _BundleSelectingFileDialog)


def test_app_bundle_detection(tmp_path):
    bundle = tmp_path / "Notes.app"
    bundle.mkdir()
    plain = tmp_path / "Utilities"
    plain.mkdir()
    script = tmp_path / "run.py"
    script.write_text("print(1)\n", encoding="utf-8")

    if sys.platform == "darwin":
        assert _is_selectable_app_bundle(str(bundle))
        assert _is_selectable_app_bundle(str(bundle) + "/")
    else:
        assert not _is_selectable_app_bundle(str(bundle))
    assert not _is_selectable_app_bundle(str(plain))
    assert not _is_selectable_app_bundle(str(script))
    assert not _is_selectable_app_bundle("")


@pytest.mark.skipif(sys.platform != "darwin", reason="app bundles are a macOS file dialog issue")
def test_accept_selects_app_bundle_instead_of_entering_it(qapp, qtbot, tmp_path):
    bundle = tmp_path / "Notes.app"
    bundle.mkdir()
    dlg = _bundle_dialog(qtbot, tmp_path)
    _select(qtbot, dlg, bundle)
    box = dlg.findChild(QDialogButtonBox)
    assert box is not None
    open_button = box.button(QDialogButtonBox.StandardButton.Open)
    assert open_button is not None
    open_button.click()

    assert dlg.result() == QDialog.DialogCode.Accepted
    assert Path(dlg.selectedFiles()[0]).resolve() == bundle.resolve()
    assert Path(dlg.directory().absolutePath()).resolve() == tmp_path.resolve()


@pytest.mark.skipif(sys.platform != "darwin", reason="app bundles are a macOS file dialog issue")
def test_highlighting_app_bundle_shows_its_name(qapp, qtbot, tmp_path):
    bundle = tmp_path / "Notes.app"
    bundle.mkdir()
    plain = tmp_path / "Utilities"
    plain.mkdir()
    dlg = _bundle_dialog(qtbot, tmp_path)
    edit = dlg.findChild(QLineEdit, "fileNameEdit")
    assert edit is not None

    _highlight(dlg, bundle)
    assert edit.text() == "Notes.app"

    edit.clear()
    _highlight(dlg, plain)
    assert edit.text() == ""


@pytest.mark.skipif(sys.platform != "darwin", reason="app bundles are a macOS file dialog issue")
def test_entering_app_bundle_selects_it(qapp, qtbot, tmp_path):
    bundle = tmp_path / "Notes.app"
    bundle.mkdir()
    dlg = _bundle_dialog(qtbot, tmp_path)

    dlg.directoryEntered.emit(str(bundle))
    qtbot.waitUntil(lambda: dlg.result() == QDialog.DialogCode.Accepted)

    assert Path(dlg.selectedFiles()[0]).resolve() == bundle.resolve()
    assert Path(dlg.directory().absolutePath()).resolve() == tmp_path.resolve()


@pytest.mark.skipif(sys.platform != "darwin", reason="app bundles are a macOS file dialog issue")
def test_plain_directory_and_script_keep_normal_file_dialog_behavior(qapp, qtbot, tmp_path):
    plain = tmp_path / "Utilities"
    plain.mkdir()
    script = tmp_path / "run.py"
    script.write_text("print(1)\n", encoding="utf-8")

    folder_dlg = _bundle_dialog(qtbot, tmp_path)
    _select(qtbot, folder_dlg, plain)
    folder_dlg.accept()
    assert folder_dlg.result() != QDialog.DialogCode.Accepted
    assert Path(folder_dlg.directory().absolutePath()).resolve() == plain.resolve()

    file_dlg = _bundle_dialog(qtbot, tmp_path, "All Files (*.*)")
    _select(qtbot, file_dlg, script)
    file_dlg.accept()
    assert file_dlg.result() == QDialog.DialogCode.Accepted
    assert Path(file_dlg.selectedFiles()[0]).resolve() == script.resolve()


def _bundle_dialog(qtbot, directory: Path, name_filter: str = "Applications (*.app)") -> _BundleSelectingFileDialog:
    dlg = _BundleSelectingFileDialog(None, "Select program or script", str(directory), name_filter)
    dlg.setFileMode(dlg.FileMode.ExistingFile)
    dlg.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    qtbot.addWidget(dlg)
    dlg.show()
    model = dlg.findChild(QFileSystemModel)
    assert model is not None
    index = model.index(str(directory))
    qtbot.waitUntil(lambda: model.rowCount(index) > 0, timeout=3000)
    return dlg


def _select(qtbot, dlg: _BundleSelectingFileDialog, path: Path) -> None:
    qtbot.waitUntil(
        lambda: _selection_is(dlg, path),
        timeout=3000,
    )


def _selection_is(dlg: _BundleSelectingFileDialog, path: Path) -> bool:
    dlg.selectFile(str(path))
    files = dlg.selectedFiles()
    return len(files) == 1 and Path(files[0]).resolve() == path.resolve()


def _highlight(dlg: _BundleSelectingFileDialog, path: Path) -> None:
    model = dlg.findChild(QFileSystemModel)
    assert model is not None
    index = model.index(str(path))
    assert index.isValid()
    view = dlg.findChild(QListView, "listView")
    assert view is not None
    view.selectionModel().setCurrentIndex(
        index,
        QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
    )
