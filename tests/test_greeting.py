"""Startup arrow size and the resize greeting."""

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QMenu

from runner.config import (
    DEFAULT_TRIGGER_HEIGHT,
    DEFAULT_TRIGGER_WIDTH,
    AppConfig,
    ConfigManager,
    Launcher,
    Settings,
)
from runner.ui.add_dialog import AddEditDialog
from runner.ui.toggle_switch import ToggleSwitch
from runner.ui.greeting import (
    StartupGreeting,
    bubble_box_size,
    ensure_visible_trigger_size,
    greeting_bubble_rect,
)
from runner.ui.greeting import GreetingBubble
from runner.ui.trigger import TriggerWidget


def test_settings_default_arrow_is_large_and_greeting_is_on():
    settings = Settings()
    assert settings.trigger_width == DEFAULT_TRIGGER_WIDTH == 120
    assert settings.trigger_height == DEFAULT_TRIGGER_HEIGHT == 96
    assert settings.show_startup_greeting is True
    assert settings.applied_visible_trigger_size is False


def test_old_config_keeps_small_arrow_until_ensure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "runner.config.platformdirs.user_config_dir",
        lambda *a, **k: str(tmp_path),
    )
    path = tmp_path / "config.json"
    path.write_text(
        """
        {
          "version": 1,
          "settings": {
            "trigger_width": 53,
            "trigger_height": 53,
            "position_x": 1674,
            "position_y": 984
          },
          "launchers": []
        }
        """,
        encoding="utf-8",
    )
    mgr = ConfigManager()
    assert mgr.config.settings.trigger_width == 53
    assert mgr.had_saved_config is True
    assert mgr.config.settings.show_startup_greeting is True
    assert mgr.config.settings.applied_visible_trigger_size is False

    ensure_visible_trigger_size(mgr)
    assert mgr.config.settings.trigger_width == DEFAULT_TRIGGER_WIDTH
    assert mgr.config.settings.trigger_height == DEFAULT_TRIGGER_HEIGHT
    assert mgr.config.settings.applied_visible_trigger_size is True
    assert mgr.config.settings.position_x == 1674

    # A later smaller choice is left alone.
    mgr.update_settings(trigger_width=70, trigger_height=60)
    ensure_visible_trigger_size(mgr)
    assert mgr.config.settings.trigger_width == 70
    assert mgr.config.settings.trigger_height == 60


def test_missing_config_is_a_first_run(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "runner.config.platformdirs.user_config_dir",
        lambda *a, **k: str(tmp_path),
    )
    mgr = ConfigManager()
    assert mgr.config.settings.trigger_width == DEFAULT_TRIGGER_WIDTH
    assert mgr.had_saved_config is False
    assert mgr.config.settings.trigger_height == DEFAULT_TRIGGER_HEIGHT
    assert (tmp_path / "config.json").exists()


def test_returning_launch_shows_border_without_bubble(qapp, qtbot):
    trigger = _shown_trigger(qtbot, 420, 280)
    greeting = StartupGreeting(show_bubble=False)
    try:
        greeting.present(trigger)
        QApplication.processEvents()
        assert trigger.width() == 120 and trigger.height() == 96
        assert trigger._greeting_highlight is True
        assert greeting.bubble.isVisible() is False
        assert greeting.border.isVisible() is True
        assert greeting.border.width() == trigger.width() + 16

        QApplication.sendEvent(trigger, QEvent(QEvent.Type.Enter))
        assert greeting.dismissed is True
        _wait_until_faded(qtbot, greeting, trigger)

        greeting.show_again(trigger)
        QApplication.processEvents()
        assert trigger._greeting_highlight is True
        assert greeting.bubble.isVisible() is False
    finally:
        greeting.shutdown()


def test_greeting_message_and_bubble_placement():
    icon = bubble_box_size()
    assert icon.width() == icon.height() >= 64
    box = QSize(260, 72)
    avail = QRect(0, 0, 1920, 1080)

    near_corner = QRect(1674, 984, 120, 96)
    rect, tail = greeting_bubble_rect(near_corner, box, avail)
    assert avail.contains(rect)
    assert not rect.intersects(near_corner.adjusted(-4, -4, 4, 4))
    assert tail == "right"

    near_origin = QRect(40, 40, 120, 96)
    rect, tail = greeting_bubble_rect(near_origin, box, avail)
    assert avail.contains(rect)
    assert not rect.intersects(near_origin)
    assert tail == "left"
    assert rect.left() > near_origin.right()


def test_greeting_shows_border_and_bubble_until_resize_or_click(qapp, qtbot):
    cfg = AppConfig()
    cfg.settings.trigger_width = 53
    cfg.settings.trigger_height = 53
    cfg.settings.position_x = 80
    cfg.settings.position_y = 80
    trigger = TriggerWidget(cfg)
    qtbot.addWidget(trigger)
    trigger.show()
    qtbot.waitExposed(trigger)

    greeting = StartupGreeting()
    try:
        greeting.present(trigger)
        QApplication.processEvents()
        assert greeting.bubble.isVisible()
        assert greeting.bubble.width() < 160
        _assert_resize_icon(greeting.bubble)
        assert trigger._greeting_highlight is True
        assert trigger._resize_margin == 14

        screen = trigger.screen() or QApplication.primaryScreen()
        if screen is not None and screen.availableGeometry().width() > 600:
            assert not greeting.bubble.frameGeometry().intersects(trigger.frameGeometry())

        # The rim sits outside the arrow, so the arrow keeps the size it was given.
        assert trigger.width() == 53 and trigger.height() == 53
        assert greeting.border.isVisible()
        assert greeting.border.width() == trigger.width() + 16
        assert greeting.border.x() == trigger.x() - 8
        trigger.repaint()
        greeting.border.repaint()
        edge = trigger.grab().toImage().pixelColor(2, trigger.height() // 2)
        assert edge.red() < 80, edge.name()
        rim = greeting.border.grab().toImage().pixelColor(3, greeting.border.height() // 2)
        assert rim.red() > 180 and rim.green() > 120, rim.name()

        greeting._on_flash()
        assert trigger._greeting_flash_on is False
        trigger.repaint()

        greeting.dismiss_for_session()
        assert greeting.dismissed is True
        _wait_until_faded(qtbot, greeting, trigger)
        assert trigger._resize_margin == 8

        # Dismissed for this launch, including another present().
        greeting.present(trigger)
        assert greeting.bubble.isVisible() is False

        greeting.show_again(trigger)
        assert greeting.bubble.isVisible() is True
        assert trigger._greeting_highlight is True
    finally:
        greeting.shutdown()


def _wait_until_faded(qtbot, greeting: StartupGreeting, trigger: TriggerWidget) -> None:
    qtbot.waitUntil(
        lambda: (
            greeting.bubble.isVisible() is False
            and greeting.border.isVisible() is False
            and trigger._greeting_highlight is False
        ),
        timeout=2000,
    )


def _shown_trigger(qtbot, x: int, y: int) -> TriggerWidget:
    cfg = AppConfig()
    cfg.settings.trigger_width = 120
    cfg.settings.trigger_height = 96
    cfg.settings.position_x = x
    cfg.settings.position_y = y
    trigger = TriggerWidget(cfg)
    qtbot.addWidget(trigger)
    trigger.show()
    qtbot.waitExposed(trigger)
    return trigger


def test_hover_or_click_hides_the_border_until_restart(qapp, qtbot):
    trigger = _shown_trigger(qtbot, 400, 300)
    greeting = StartupGreeting()
    try:
        greeting.present(trigger)
        QApplication.processEvents()
        assert trigger._greeting_highlight is True
        assert greeting.bubble.isVisible() is True

        QApplication.sendEvent(trigger, QEvent(QEvent.Type.Enter))
        assert greeting.dismissed is True
        assert greeting.bubble.isVisible() is True
        assert trigger._greeting_highlight is True

        greeting.present(trigger)
        assert greeting.bubble.isVisible() is True
        _wait_until_faded(qtbot, greeting, trigger)
        greeting.present(trigger)
        assert greeting.bubble.isVisible() is False
        assert trigger._greeting_highlight is False
    finally:
        greeting.shutdown()

    trigger = _shown_trigger(qtbot, 500, 300)
    greeting = StartupGreeting()
    try:
        greeting.present(trigger)
        QApplication.processEvents()
        assert trigger._greeting_highlight is True
        center = QPoint(trigger.width() // 2, trigger.height() // 2)
        qtbot.mouseClick(trigger, Qt.MouseButton.LeftButton, pos=center)
        assert greeting.dismissed is True
        _wait_until_faded(qtbot, greeting, trigger)
        greeting.present(trigger)
        assert trigger._greeting_highlight is False
    finally:
        greeting.shutdown()


def test_dismiss_fades_the_warning_over_about_a_second(qapp, qtbot):
    trigger = _shown_trigger(qtbot, 640, 360)
    greeting = StartupGreeting()
    try:
        greeting.present(trigger)
        QApplication.processEvents()
        greeting.dismiss_for_session()
        assert greeting.bubble.isVisible() is True
        assert trigger._greeting_opacity == 1.0

        qtbot.wait(400)
        assert greeting.bubble.isVisible() is True
        assert trigger._greeting_highlight is True
        assert 0.15 < trigger._greeting_opacity < 0.9
        assert 0.15 < greeting.bubble._opacity < 0.9

        _wait_until_faded(qtbot, greeting, trigger)
        assert trigger._greeting_opacity == 1.0
        greeting.present(trigger)
        assert greeting.bubble.isVisible() is False
    finally:
        greeting.shutdown()


def test_arrow_already_under_the_pointer_skips_the_border(qapp, qtbot):
    cursor = QCursor.pos()
    trigger = _shown_trigger(qtbot, cursor.x(), cursor.y())
    greeting = StartupGreeting()
    try:
        greeting.present(trigger)
        assert greeting.dismissed is True
        assert greeting.bubble.isVisible() is False
        assert trigger._greeting_highlight is False
    finally:
        greeting.shutdown()


def _assert_resize_icon(bubble: GreetingBubble) -> None:
    """The diagonal glyph is dark, and the bubble fill around it stays yellow."""
    bubble.repaint()
    image = bubble.grab().toImage()
    box_left = 16  # tail sits on the left until the bubble is placed
    center = image.pixelColor(box_left + (image.width() - box_left) // 2, image.height() // 2)
    assert center.red() < 90 and center.green() < 90 and center.blue() < 90, center.name()
    yellow = image.pixelColor(image.width() - 18, 22)
    assert yellow.red() > 180 and yellow.green() > 140, yellow.name()


def test_bubble_click_dismisses_for_this_launch(qapp, qtbot):
    bubble = GreetingBubble()
    qtbot.addWidget(bubble)
    seen = []
    bubble.set_dismiss_handler(lambda: seen.append("dismiss"))
    bubble.show()
    qtbot.mouseClick(bubble, Qt.MouseButton.LeftButton)
    assert seen == ["dismiss"]
    assert bubble_box_size(bubble.font()).width() > 40


def test_greeting_switch_is_on_the_arrow_menu(qapp, qtbot):
    cfg = AppConfig()
    cfg.settings.show_startup_greeting = True
    trigger = TriggerWidget(cfg)
    qtbot.addWidget(trigger)
    trigger.show()
    seen = []
    trigger.greeting_toggled.connect(seen.append)

    trigger._show_context_menu(QPoint(12, 12))
    menu = trigger.findChildren(QMenu)[-1]
    qtbot.addWidget(menu)
    switches = [w for w in menu.findChildren(ToggleSwitch) if w.text() == "Show greeting message"]
    assert len(switches) == 1
    switch = switches[0]
    assert switch.isChecked() is True
    assert seen == []

    switch.click()
    assert seen == [False]
    assert switch.isChecked() is False
    menu.close()

    existing = Launcher.new("Calc", "calc")
    edit = AddEditDialog(existing)
    qtbot.addWidget(edit)
    add = AddEditDialog(None)
    qtbot.addWidget(add)
    for dialog in (edit, add):
        labels = [w.text() for w in dialog.findChildren(ToggleSwitch)]
        assert "Show greeting message" not in labels
