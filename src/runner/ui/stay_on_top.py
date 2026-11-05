"""Keep dialogs above the always-on-top arrow.

The arrow, lists, and greeting use WindowStaysOnTopHint. On Windows an owned
dialog without that flag is not topmost, so it opens behind the arrow. With
the flag, a later raise of the arrow still covers the dialog, because every
topmost window shares one band.

On macOS Qt maps that flag to NSModalPanelWindowLevel, the same level as the
arrow. A modal dialog does not push those peers backward, so the arrow and
lists can sit on top of Add, Edit, and Manage. The dialog is lifted to
NSStatusWindowLevel, above that band and still under popup menus.

On macOS the same flag makes Qt skip the native open panel and use its own
file dialog. The widget dialog treats an .app bundle as a folder, so choosing
Notes.app walks into the bundle. The macOS open dialog accepts the bundle as
the selected program instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QLineEdit, QMenu, QMessageBox, QWidget

# Above NSModalPanelWindowLevel (8), below NSPopUpMenuWindowLevel (101).
_NS_STATUS_WINDOW_LEVEL = 25
_MARK_PROP = "_runnerStayAbove"
_SURFACE_PROP = "_runnerStayUnderDialogs"

_visible: list[QWidget] = []
_lift_pending = False
_in_lift = False
_swallow_surface_events = False
_dialog_filter: QObject | None = None
_surface_filter: QObject | None = None


def open_editing_dialogs() -> list[QWidget]:
    """Dialogs currently kept above the arrow and the lists."""
    return [widget for widget in _visible if _alive(widget) and widget.isVisible()]


def mark_stay_on_top(widget: QWidget) -> None:
    widget.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    if widget.property(_MARK_PROP):
        return
    widget.setProperty(_MARK_PROP, True)
    widget.installEventFilter(_filters()[0])


def _filters() -> tuple[QObject, QObject]:
    global _dialog_filter, _surface_filter
    if _dialog_filter is None or _surface_filter is None:
        parent = QApplication.instance()
        _dialog_filter = _EditingDialogFilter(parent)
        _surface_filter = _RunnerSurfaceFilter(parent)
    return _dialog_filter, _surface_filter


def _alive(widget: QWidget) -> bool:
    try:
        widget.isVisible()
    except RuntimeError:
        return False
    return True


def _register(widget: QWidget) -> None:
    if not _alive(widget):
        return
    if widget in _visible:
        _visible.remove(widget)
    _visible.append(widget)
    _watch_surfaces()
    _schedule_lift()


def _unregister(widget: QWidget) -> None:
    if widget in _visible:
        _visible.remove(widget)


def _watch_surfaces() -> None:
    app = QApplication.instance()
    if app is None:
        return
    surface_filter = _filters()[1]
    for widget in app.topLevelWidgets():
        if not _is_runner_surface(widget) or widget.property(_SURFACE_PROP):
            continue
        widget.setProperty(_SURFACE_PROP, True)
        widget.installEventFilter(surface_filter)


def _is_runner_surface(widget: QWidget) -> bool:
    if not isinstance(widget, QWidget) or not widget.isWindow():
        return False
    if widget.property(_MARK_PROP):
        return False
    flags = widget.windowFlags()
    if flags & Qt.WindowType.Popup:
        return False
    return bool(flags & Qt.WindowType.WindowStaysOnTopHint)


def _schedule_lift() -> None:
    global _lift_pending
    if _lift_pending or not _visible:
        return
    _lift_pending = True
    QTimer.singleShot(0, _lift_now)


def _lift_now() -> None:
    global _lift_pending, _in_lift, _swallow_surface_events
    _lift_pending = False
    _in_lift = True
    # raise_() posts z-order events. Swallow those so the lift does not schedule another lift.
    _swallow_surface_events = True
    try:
        for widget in list(_visible):
            if not _alive(widget) or not widget.isVisible():
                _unregister(widget)
                continue
            widget.raise_()
            _lift_native(widget)
    finally:
        _in_lift = False
    QTimer.singleShot(0, _stop_swallowing_surface_events)


def _stop_swallowing_surface_events() -> None:
    global _swallow_surface_events
    _swallow_surface_events = False


def _lift_native(widget: QWidget) -> None:
    """Put widget above other topmost Runner windows on the real platform."""
    app = QApplication.instance()
    if app is None or not _alive(widget):
        return
    platform = app.platformName()
    if platform == "cocoa":
        _set_mac_window_level(widget, _NS_STATUS_WINDOW_LEVEL)
    elif platform == "windows":
        _set_windows_topmost(widget)


def _set_mac_window_level(widget: QWidget, level: int) -> None:
    import ctypes
    from ctypes import c_long, c_void_p

    view = int(widget.winId() or 0)
    if not view:
        return
    objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
    objc.sel_registerName.restype = c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    get_window = ctypes.cast(objc.objc_msgSend, ctypes.CFUNCTYPE(c_void_p, c_void_p, c_void_p))
    set_level = ctypes.cast(
        objc.objc_msgSend,
        ctypes.CFUNCTYPE(c_void_p, c_void_p, c_void_p, c_long),
    )
    window = get_window(c_void_p(view), objc.sel_registerName(b"window"))
    if not window:
        return
    set_level(window, objc.sel_registerName(b"setLevel:"), level)


def _set_windows_topmost(widget: QWidget) -> None:
    import ctypes

    hwnd = int(widget.winId() or 0)
    if not hwnd:
        return
    user32 = ctypes.windll.user32
    user32.SetWindowPos.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.SetWindowPos.restype = ctypes.c_int
    hwnd_topmost = ctypes.c_void_p(-1)
    no_move, no_size, no_activate = 0x0002, 0x0001, 0x0010
    user32.SetWindowPos(hwnd, hwnd_topmost, 0, 0, 0, 0, no_move | no_size | no_activate)


class _EditingDialogFilter(QObject):
    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if not isinstance(obj, QWidget) or isinstance(obj, QMenu):
            return False
        kind = event.type()
        if kind in (QEvent.Type.Show, QEvent.Type.WindowActivate):
            _register(obj)
        elif kind in (QEvent.Type.Hide, QEvent.Type.Close):
            _unregister(obj)
        return False


class _RunnerSurfaceFilter(QObject):
    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if _in_lift or _swallow_surface_events or not _visible:
            return False
        if event.type() == QEvent.Type.ZOrderChange:
            _schedule_lift()
        return False


class StayOnTopDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        mark_stay_on_top(self)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        _register(self)


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
