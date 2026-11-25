"""Keep dialogs above the always-on-top arrow.

The arrow, lists, and greeting use WindowStaysOnTopHint. On Windows an owned
dialog without that flag is not topmost, so it opens behind the arrow. With
the flag, a later raise of the arrow still covers the dialog, because every
topmost window shares one band.

On macOS Qt maps that flag to NSModalPanelWindowLevel, the same level as the
arrow. A modal dialog does not push those peers backward, so the arrow and
lists can sit on top of Add, Edit, and Manage. The dialog is lifted to
NSStatusWindowLevel, above that band and still under popup menus.

Dialogs also open clear of the arrow, the open lists, and other open dialogs
when the screen has room, instead of centred on the arrow and covering it.
See place_clear_of_runner.

Right-click menus need the opposite on macOS: a popup menu already sits at
NSPopUpMenuWindowLevel, above every Runner window, and the stay-on-top flag
pulls it down to the lists' level, so a list could cover its own row menu.
keep_menu_above_lists sets the flag only where it helps.

On macOS the same flag makes Qt skip the native open panel and use its own
file dialog. The widget dialog treats an .app bundle as a folder, so choosing
Notes.app walks into the bundle. The macOS open dialog accepts the bundle as
the selected program instead.
"""

from __future__ import annotations

import sys
import weakref
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QLineEdit, QMenu, QMessageBox, QWidget

from .theme import style_dialog

# Above NSModalPanelWindowLevel (8), below NSPopUpMenuWindowLevel (101).
_NS_STATUS_WINDOW_LEVEL = 25
_MARK_PROP = "_runnerStayAbove"
_SURFACE_PROP = "_runnerStayUnderDialogs"
_PLACED_PROP = "_runnerPlacedClear"
# Space between a dialog and the Runner window it steps aside from.
_CLEAR_GAP = 12
# macOS title bar, for a dialog whose frame is not known before its first show.
_TITLE_BAR_GUESS = 28

_visible: list[QWidget] = []
_lift_pending = False
_in_lift = False
_swallow_surface_events = False
_dialog_filter: QObject | None = None
# Run when a dialog first opens, before it is placed. Runner closes its
# hover lists here so the dialog does not open over them.
_on_dialog_open: list = []
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


def on_dialog_open(callback) -> None:
    """Call callback() each time a dialog, message box, or file browser first opens.

    A bound method is held weakly, so its owner can go away without unhooking.
    """
    ref = weakref.WeakMethod(callback) if hasattr(callback, "__self__") else (lambda: callback)
    _on_dialog_open.append(ref)


def keep_menu_above_lists(menu: QMenu) -> None:
    """Make a list's right-click menu open above every list.

    Windows and Linux need the stay-on-top flag for that. On macOS a popup
    menu is already above the lists, and the flag would put it level with them.
    """
    app = QApplication.instance()
    if app is not None and app.platformName() == "cocoa":
        return
    menu.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)


def runner_windows_to_avoid(exclude: QWidget | None = None) -> list[QRect]:
    """Screen rects of the visible arrow, lists, greeting, and open dialogs."""
    app = QApplication.instance()
    if app is None:
        return []
    rects: list[QRect] = []
    for widget in app.topLevelWidgets():
        # A list still fading in counts, even at opacity 0: it is about to be seen.
        if widget is exclude or not widget.isVisible() or isinstance(widget, QMenu):
            continue
        # A dialog's own parent window counts too: it should stay in view.
        if _is_runner_surface(widget) or widget.property(_MARK_PROP):
            rects.append(widget.frameGeometry())
    return [rect for rect in rects if rect.isValid() and not rect.isEmpty()]


def clear_position(size: QRect, avoid: list[QRect], avail: QRect, gap: int = _CLEAR_GAP) -> QPoint:
    """Top-left for a window of size.size() that covers none of avoid, if any spot on avail does.

    size is where the window would open by default; that spot is tried first
    and ties go to the spot nearest it, so a dialog stays near what opened it.
    When every spot covers something, the one that covers the least wins.
    """
    w, h = size.width(), size.height()
    start = size.topLeft()
    candidates = [QPoint(start)]
    for rect in avoid:
        for x in (rect.right() + 1 + gap, rect.left() - gap - w, rect.left(), rect.right() + 1 - w,
                  rect.center().x() - w // 2):
            for y in (rect.bottom() + 1 + gap, rect.top() - gap - h, rect.top(), rect.bottom() + 1 - h,
                      rect.center().y() - h // 2):
                candidates.append(QPoint(x, y))
    candidates += [
        QPoint(avail.left(), avail.top()),
        QPoint(avail.right() + 1 - w, avail.top()),
        QPoint(avail.left(), avail.bottom() + 1 - h),
        QPoint(avail.right() + 1 - w, avail.bottom() + 1 - h),
        QPoint(avail.center().x() - w // 2, avail.center().y() - h // 2),
    ]

    def clamp(point: QPoint) -> QPoint:
        x = max(avail.left(), min(point.x(), avail.right() + 1 - w))
        y = max(avail.top(), min(point.y(), avail.bottom() + 1 - h))
        return QPoint(x, y)

    def covered(point: QPoint) -> int:
        rect = QRect(point, size.size())
        total = 0
        for other in avoid:
            part = rect.intersected(other)
            if not part.isEmpty():
                total += part.width() * part.height()
        return total

    def distance(point: QPoint) -> int:
        return (point - start).manhattanLength()

    return min((clamp(point) for point in candidates), key=lambda point: (covered(point), distance(point)))


def place_clear_of_runner(widget: QWidget) -> None:
    """Move a dialog off the arrow, the open lists, and other open dialogs.

    Done once, when it first opens. After that it stays where the user puts it.
    The on_dialog_open callbacks run first, so lists they close are not avoided.
    """
    if not _alive(widget) or widget.property(_PLACED_PROP):
        return
    widget.setProperty(_PLACED_PROP, True)
    for ref in list(_on_dialog_open):
        callback = ref()
        if callback is None:
            _on_dialog_open.remove(ref)
            continue
        try:
            callback()
        except RuntimeError:  # its windows were already deleted
            _on_dialog_open.remove(ref)
    avoid = runner_windows_to_avoid(exclude=widget)
    if not avoid:
        return
    frame = QRect(widget.frameGeometry())
    if frame == widget.geometry() and not widget.windowFlags() & Qt.WindowType.FramelessWindowHint:
        frame.setTop(frame.top() - _TITLE_BAR_GUESS)
    parent = widget.parentWidget()
    owner = parent.window() if parent is not None else None
    screen = (owner.screen() if owner is not None else None) or widget.screen() or QApplication.primaryScreen()
    if screen is None:
        return
    avail = screen.availableGeometry()
    # Start where Qt would open it, centred on what opened it. Some windows,
    # such as a message box, have no position of their own yet at this point.
    over = owner.frameGeometry() if owner is not None and owner.isVisible() else avail
    frame.moveCenter(over.center())
    target = clear_position(frame, avoid, avail)
    # move() places the frame, title bar included.
    widget.move(target)


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
    # Compare the window type, not single bits: Tool (0x0b) contains every bit
    # of Popup (0x09), so a bit test treats the arrow and lists as popups.
    if (flags & Qt.WindowType.WindowType_Mask) == Qt.WindowType.Popup:
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

    try:
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
    except (OSError, AttributeError, ValueError):
        return


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
        if kind == QEvent.Type.Show and obj.isWindow():
            place_clear_of_runner(obj)
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
        style_dialog(self)

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
    style_dialog(box)
    box.exec()


def question(
    parent: QWidget | None,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton,
) -> QMessageBox.StandardButton:
    # No icon: the system's question mark is drawn dark and disappears on
    # the Dark and Medium schemes, and the question says enough on its own.
    box = QMessageBox(QMessageBox.Icon.NoIcon, title, text, buttons, parent)
    mark_stay_on_top(box)
    style_dialog(box)
    return QMessageBox.StandardButton(box.exec())


def choice(
    parent: QWidget | None,
    title: str,
    text: str,
    accept_label: str,
    reject_label: str,
) -> bool:
    """A warning with two named buttons. True when the first one is chosen.

    The first button is the default, so Enter picks it. Esc picks the second.
    The text up to the first blank line is the headline; the rest is the detail.
    """
    headline, _, detail = text.partition("\n\n")
    box = QMessageBox(QMessageBox.Icon.Warning, title, headline, QMessageBox.StandardButton.NoButton, parent)
    if detail:
        box.setInformativeText(detail)
    accept = box.addButton(accept_label, QMessageBox.ButtonRole.AcceptRole)
    reject = box.addButton(reject_label, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(accept)
    box.setEscapeButton(reject)
    mark_stay_on_top(box)
    style_dialog(box)
    box.exec()
    return box.clickedButton() is accept


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
