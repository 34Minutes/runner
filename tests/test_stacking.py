"""Nothing Runner opens sits over, or hides behind, something else it has open."""

from unittest.mock import MagicMock

from PySide6.QtCore import QEvent, QRect, QSize
from PySide6.QtWidgets import QApplication

from runner.config import ConfigManager, ContainerGroup, ContainerMember, Launcher
from runner.controller import RunnerController
from runner.ui.greeting import greeting_bubble_rect
from runner.ui.stay_on_top import StayOnTopDialog, clear_position

SCREEN = QRect(0, 25, 1440, 875)


def _controller(qapp, monkeypatch, *, pinned=False) -> RunnerController:
    cfg = ConfigManager()
    alpha = Launcher.new("Alpha", "a")
    cfg.config.launchers = [alpha, Launcher.new("Beta", "b")]
    cfg.config.container_groups = [ContainerGroup.new("Projects", [ContainerMember(alpha.id)])]
    cfg.config.settings.pinned_open = pinned
    cfg.config.settings.position_x, cfg.config.settings.position_y = 400, 300
    monkeypatch.setattr("runner.controller.create_tray", lambda **_: MagicMock())
    ctl = RunnerController(qapp, cfg)
    ctl.greeting.dismiss_for_session()
    return ctl


def _dialog(ctl: RunnerController) -> StayOnTopDialog:
    # A QMessageBox shown without exec() blocks processEvents() on macOS, so use a plain dialog.
    box = StayOnTopDialog(ctl.trigger)
    box.resize(300, 160)
    return box


def _close(ctl: RunnerController) -> None:
    for panel in ctl._all_lists():
        panel.force_hide()
    ctl.trigger.hide()


def test_a_dialog_opens_beside_the_arrow_and_list_not_over_them():
    arrow = QRect(600, 300, 115, 75)
    listing = QRect(547, 372, 220, 300)
    centred_on_arrow = QRect(0, 0, 420, 360)
    centred_on_arrow.moveCenter(arrow.center())
    spot = clear_position(centred_on_arrow, [arrow, listing], SCREEN)
    placed = QRect(spot, centred_on_arrow.size())
    assert SCREEN.contains(placed)
    assert not placed.intersects(arrow)
    assert not placed.intersects(listing)
    # Still near what opened it, not thrown into a far corner.
    assert (spot - centred_on_arrow.topLeft()).manhattanLength() < 600


def test_a_dialog_with_nothing_to_avoid_stays_where_it_opens():
    start = QRect(500, 300, 400, 300)
    assert clear_position(start, [], SCREEN) == start.topLeft()


def test_with_no_clear_spot_a_dialog_covers_as_little_as_it_can():
    wall = QRect(SCREEN.left(), SCREEN.top(), 1200, SCREEN.height())
    start = QRect(100, 100, 400, 300)
    placed = QRect(clear_position(start, [wall], SCREEN), start.size())
    assert SCREEN.contains(placed)
    assert placed.left() == SCREEN.right() + 1 - placed.width()


def test_the_greeting_bubble_takes_a_side_no_list_is_on():
    arrow = QRect(600, 300, 115, 75)
    box = QSize(180, 50)
    first, _side = greeting_bubble_rect(arrow, box, SCREEN)
    rect, side = greeting_bubble_rect(arrow, box, SCREEN, avoid=[first.adjusted(-2, -2, 2, 2)])
    assert not rect.intersects(first)
    assert not rect.intersects(arrow)
    assert side != _side


def test_the_greeting_bubble_still_shows_when_every_side_is_taken():
    arrow = QRect(600, 300, 115, 75)
    rect, _side = greeting_bubble_rect(arrow, QSize(180, 50), SCREEN, avoid=[SCREEN])
    assert SCREEN.contains(rect)
    assert not rect.intersects(arrow)


def test_opening_a_dialog_closes_the_hover_lists(qapp, qtbot, monkeypatch):
    ctl = _controller(qapp, monkeypatch)
    ctl.trigger.show()
    try:
        ctl._on_trigger_enter()
        ctl._show_container_menu(ctl.cfg.config.container_groups[0].id)
        assert ctl.dropdown.isVisible() and ctl.container_panel.isVisible()
        box = _dialog(ctl)
        box.show()
        qapp.processEvents()
        assert not ctl.dropdown.isVisible()
        assert not ctl.container_panel.isVisible()
        box.close()
    finally:
        _close(ctl)


def test_opening_a_dialog_keeps_a_pinned_list_and_steps_around_it(qapp, qtbot, monkeypatch):
    ctl = _controller(qapp, monkeypatch, pinned=True)
    ctl.trigger.show()
    try:
        ctl._apply_pinned_state()
        ctl._show_container_menu(ctl.cfg.config.container_groups[0].id)
        assert ctl.dropdown.isVisible()
        box = _dialog(ctl)
        box.show()
        qapp.processEvents()
        assert ctl.dropdown.isVisible()
        assert not ctl.container_panel.isVisible()
        assert not box.frameGeometry().intersects(ctl.dropdown.frameGeometry())
        assert not box.frameGeometry().intersects(ctl.trigger.frameGeometry())
        box.close()
    finally:
        _close(ctl)


def test_a_list_that_takes_focus_puts_the_arrow_back_on_top(qapp, qtbot, monkeypatch):
    """On macOS the window that becomes active is brought to the front after earlier raises."""
    ctl = _controller(qapp, monkeypatch)
    ctl.trigger.show()
    try:
        ctl._on_trigger_enter()
        raised = []
        monkeypatch.setattr(ctl.trigger, "raise_", lambda: raised.append("arrow"))
        QApplication.sendEvent(ctl.dropdown, QEvent(QEvent.Type.WindowActivate))
        qtbot.waitUntil(lambda: "arrow" in raised, timeout=1000)
    finally:
        _close(ctl)


def test_the_greeting_rim_and_bubble_go_above_the_lists_and_under_the_arrow(qapp, qtbot, monkeypatch):
    ctl = _controller(qapp, monkeypatch, pinned=True)
    ctl.trigger.show()
    try:
        ctl._apply_pinned_state()
        order: list[str] = []
        for name, widget in (("arrow", ctl.trigger), ("rim", ctl.greeting.border),
                             ("bubble", ctl.greeting.bubble), ("list", ctl.dropdown)):
            monkeypatch.setattr(widget, "raise_", lambda name=name: order.append(name))
        ctl.greeting.show_again(ctl.trigger, show_bubble=True, even_under_pointer=True)
        order.clear()
        ctl._keep_arrow_on_top(ctl.dropdown)
        # Raised bottom to top: the last raise is the front window.
        assert order[-1] == "arrow"
        assert order.index("bubble") < order.index("rim") < len(order) - 1
        assert "list" not in order
        bubble = ctl.greeting.bubble.frameGeometry()
        assert not bubble.intersects(ctl.dropdown.frameGeometry())
    finally:
        ctl.greeting.dismiss_for_session()
        _close(ctl)

