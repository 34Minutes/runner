"""Drag rows in the dropdown to reorder launchers."""

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from runner.config import AppConfig, Launcher
from runner.ui.dropdown import DropdownPanel, _DRAG_LIFT_X, merge_visible_order
from runner.ui.launch_button import LaunchButton


def test_merge_keeps_disabled_and_filtered_rows():
    # A and C are the visible rows. B is disabled. D is enabled but filtered out.
    entries = [("A", True), ("B", False), ("D", False), ("C", True)]
    assert merge_visible_order(entries, ["C", "A"]) == ["C", "B", "D", "A"]
    assert merge_visible_order(entries, ["A", "C"]) == ["A", "B", "D", "C"]


def test_click_still_launches(qapp, qtbot):
    cfg = AppConfig()
    panel = DropdownPanel(cfg)
    qtbot.addWidget(panel)
    launcher = Launcher.new("Alpha", "alpha")
    cfg.launchers = [launcher]
    panel.rebuild_buttons([launcher])
    panel.show()
    qtbot.waitExposed(panel)

    launched = []
    panel.launch_requested.connect(lambda item: launched.append(item.name))
    button = next(b for b in panel._buttons if isinstance(b, LaunchButton))
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert launched == ["Alpha"]


def _send_mouse(button, kind, global_pos, button_state, buttons_state):
    local = button.mapFromGlobal(global_pos)
    event = QMouseEvent(
        kind,
        QPointF(local),
        QPointF(global_pos),
        button_state,
        buttons_state,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(button, event)


def test_drag_reorders_without_launching(qapp, qtbot):
    cfg = AppConfig()
    panel = DropdownPanel(cfg)
    qtbot.addWidget(panel)
    alpha = Launcher.new("Alpha", "a")
    hidden = Launcher.new("Hidden", "h", enabled=False)
    beta = Launcher.new("Beta", "b")
    gamma = Launcher.new("Gamma", "g")
    cfg.launchers = [alpha, hidden, beta, gamma]
    panel.rebuild_buttons([alpha, beta, gamma])
    panel.resize(220, 280)
    panel.show()
    qtbot.waitExposed(panel)
    QApplication.processEvents()

    buttons = [b for b in panel._buttons if isinstance(b, LaunchButton)]
    assert [b.launcher.name for b in buttons] == ["Alpha", "Beta", "Gamma"]
    tops = [b.mapToGlobal(b.rect().topLeft()).y() for b in buttons]
    assert tops[0] < tops[1] < tops[2], tops

    launched = []
    reordered = []
    panel.launch_requested.connect(lambda item: launched.append(item.name))
    panel.reordered.connect(reordered.append)

    gamma_button = buttons[2]
    press_at = gamma_button.mapToGlobal(gamma_button.rect().center())
    above_alpha = buttons[0].mapToGlobal(buttons[0].rect().topLeft())
    above_alpha.setY(above_alpha.y() - 4)

    try:
        _send_mouse(
            gamma_button,
            QEvent.Type.MouseButtonPress,
            press_at,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
        )
        _send_mouse(
            gamma_button,
            QEvent.Type.MouseMove,
            above_alpha,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
        )
        assert panel._drag_active is True
        assert gamma_button.property("dragging") == "true"
        assert "border: 4px solid rgba(255, 220, 70, 240)" in gamma_button.styleSheet()
        assert [b.launcher.name for b in panel._drag_order] == ["Gamma", "Alpha", "Beta"]
        assert gamma_button.x() == buttons[0].x() + _DRAG_LIFT_X
        alpha_shift = panel._row_anims.get(buttons[0])
        assert alpha_shift is not None
        assert alpha_shift.endValue().y() > alpha_shift.startValue().y()
        _send_mouse(
            gamma_button,
            QEvent.Type.MouseButtonRelease,
            above_alpha,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
        )
    finally:
        panel._cancel_drag()

    names = [b.launcher.name for b in panel._buttons if isinstance(b, LaunchButton)]
    assert names == ["Gamma", "Alpha", "Beta"]
    assert launched == []
    assert reordered == [[gamma.id, hidden.id, alpha.id, beta.id]]

    # Drag the top row downward past the last row.
    cfg.launchers = [gamma, hidden, alpha, beta]
    top = next(b for b in panel._buttons if isinstance(b, LaunchButton) and b.launcher.name == "Gamma")
    last = next(b for b in panel._buttons if isinstance(b, LaunchButton) and b.launcher.name == "Beta")
    QApplication.processEvents()
    start = top.mapToGlobal(top.rect().center())
    below = last.mapToGlobal(last.rect().bottomLeft())
    below.setY(below.y() + 8)
    try:
        _send_mouse(top, QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
        _send_mouse(top, QEvent.Type.MouseMove, below, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
        _send_mouse(top, QEvent.Type.MouseButtonRelease, below, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    finally:
        panel._cancel_drag()

    names = [b.launcher.name for b in panel._buttons if isinstance(b, LaunchButton)]
    assert names == ["Alpha", "Beta", "Gamma"]
    assert launched == []
    assert reordered[-1] == [alpha.id, hidden.id, beta.id, gamma.id]


def test_highlighted_row_lifts_with_a_yellow_border(qapp, qtbot):
    cfg = AppConfig()
    panel = DropdownPanel(cfg)
    qtbot.addWidget(panel)
    alpha = Launcher.new("Alpha", "a")
    beta = Launcher.new("Beta", "b")
    cfg.launchers = [alpha, beta]
    panel.rebuild_buttons([alpha, beta])
    panel.resize(220, 200)
    panel.show()
    qtbot.waitExposed(panel)
    QApplication.processEvents()

    buttons = [b for b in panel._buttons if isinstance(b, LaunchButton)]
    panel._set_keyboard_current(buttons[0])
    highlighted = buttons[0]
    neighbour = buttons[1]
    assert highlighted.property("kbSelected") == "true"
    start = highlighted.mapToGlobal(highlighted.rect().center())
    nudged = QPoint(start.x(), start.y() + 16)
    try:
        _send_mouse(
            highlighted,
            QEvent.Type.MouseButtonPress,
            start,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
        )
        _send_mouse(
            highlighted,
            QEvent.Type.MouseMove,
            nudged,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
        )
        assert panel._drag_active is True
        assert highlighted.property("dragging") == "true"
        assert highlighted.x() == neighbour.x() + _DRAG_LIFT_X
        image = highlighted.grab().toImage()
        color = image.pixelColor(2, image.height() // 2)
        assert color.red() > 200 and color.green() > 150 and color.blue() < 140, color.name()
    finally:
        panel._cancel_drag()
