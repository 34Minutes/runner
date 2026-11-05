"""Right-click Edit and Delete on a dropdown row."""

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QApplication

from runner.config import AppConfig, Launcher
from runner.ui.dropdown import DropdownPanel
from runner.ui.launch_button import LaunchButton


def _send_context_menu(button: LaunchButton) -> None:
    """QTest's right-click does not synthesize a context-menu event."""
    local = QPoint(button.width() // 2, button.height() // 2)
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, local, button.mapToGlobal(local))
    QApplication.sendEvent(button, event)


def test_right_click_offers_edit_and_delete(qapp, qtbot):
    cfg = AppConfig()
    panel = DropdownPanel(cfg)
    qtbot.addWidget(panel)
    alpha = Launcher.new("Alpha", "a")
    beta = Launcher.new("Beta", "b")
    cfg.launchers = [alpha, beta]
    panel.rebuild_buttons([alpha, beta])
    panel.show()
    qtbot.waitExposed(panel)

    edited = []
    deleted = []
    launched = []
    panel.edit_requested.connect(edited.append)
    panel.delete_requested.connect(deleted.append)
    panel.launch_requested.connect(lambda item: launched.append(item.name))

    button = next(b for b in panel._buttons if isinstance(b, LaunchButton) and b.launcher.name == "Beta")
    assert button.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
    qtbot.mouseClick(button, Qt.MouseButton.RightButton)
    assert launched == []
    assert panel._drag_active is False

    _send_context_menu(button)

    menu = panel._item_menu
    assert menu is not None
    assert [action.text() for action in menu.actions()] == ["Edit", "Delete"]
    assert menu.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert panel._in_context_menu is True

    # Popup is deferred so a frameless tool window does not dismiss it on macOS.
    QApplication.processEvents()

    actions = menu.actions()
    actions[0].trigger()
    assert edited == [beta]

    actions[1].trigger()
    assert deleted == [beta]
    assert launched == []

    menu.close()


def test_open_item_menu_keeps_the_list_from_hiding(qapp, qtbot):
    cfg = AppConfig()
    cfg.settings.pinned_open = False
    panel = DropdownPanel(cfg)
    qtbot.addWidget(panel)
    launcher = Launcher.new("Alpha", "a")
    panel.rebuild_buttons([launcher])
    panel.show()
    qtbot.waitExposed(panel)

    panel._in_context_menu = True
    panel.leaveEvent(QEvent(QEvent.Type.Leave))
    assert panel._hide_timer.isActive() is False
