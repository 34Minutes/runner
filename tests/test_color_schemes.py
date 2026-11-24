"""Color schemes: Dark stays the default, Bright and Medium are optional."""

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QMenu

from runner.config import AppConfig, ConfigManager, Launcher
from runner.ui.dropdown import DropdownPanel
from runner.ui.group_dialog import _DRAG_BORDER, _SELECTED_BG, _SELECTED_FG
from runner.ui.theme import DARK, SCHEMES, current, launch_button_qss, resolve, use
from runner.ui.trigger import MenuSlider, TriggerWidget


@pytest.fixture(autouse=True)
def _reset_theme():
    use("dark")
    yield
    use("dark")


def _arrow_menu(trigger):
    found = [
        menu
        for menu in trigger.findChildren(QMenu)
        if any(action.text() == "Exit" for action in menu.actions())
    ]
    assert found
    return found[-1]


def test_dark_is_the_default_and_keeps_the_yellow_highlight():
    assert [scheme.id for scheme in SCHEMES] == ["dark", "medium", "bright"]
    assert [scheme.label for scheme in SCHEMES] == ["Dark", "Medium", "Bright"]
    assert current().id == "dark"
    assert resolve(None).id == "dark"
    assert resolve("nope").id == "dark"
    assert DARK.dialog_drag_border == _DRAG_BORDER
    assert DARK.dialog_selected_bg == _SELECTED_BG
    assert DARK.dialog_selected_fg == _SELECTED_FG
    assert "border: 4px solid rgba(255, 220, 70, 240)" in launch_button_qss()


def test_missing_scheme_in_an_old_config_stays_dark(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "runner.config.platformdirs.user_config_dir",
        lambda *args, **kwargs: str(tmp_path),
    )
    mgr = ConfigManager()
    assert mgr.config.settings.color_scheme == "dark"
    loaded = AppConfig.from_dict({"version": 1, "settings": {"position_x": 4}, "launchers": []})
    assert loaded.settings.color_scheme == "dark"
    mgr.update_settings(color_scheme="medium")
    assert ConfigManager().config.settings.color_scheme == "medium"


def test_opacity_and_decay_sliders_report_the_new_value(qapp, qtbot):
    cfg = AppConfig()
    cfg.settings.opacity_percent = 80
    cfg.settings.decay_ms = 400
    trigger = TriggerWidget(cfg)
    qtbot.addWidget(trigger)
    opacity_seen = []
    decay_seen = []
    trigger.window_opacity_changed.connect(opacity_seen.append)
    trigger.decay_changed.connect(decay_seen.append)
    trigger._show_context_menu(QPoint(8, 8))
    menu = _arrow_menu(trigger)
    qtbot.addWidget(menu)
    rows = {slider.objectName(): slider for slider in menu.findChildren(MenuSlider)}
    assert rows["Opacity"].slider().value() == 80
    assert rows["Decay rate"].slider().value() == 400
    assert rows["Decay rate"].slider().invertedAppearance() is True
    rows["Opacity"].slider().setValue(45)
    rows["Decay rate"].slider().setValue(1000)
    assert opacity_seen == [45]
    assert decay_seen == [1000]
    menu.close()


def test_color_schemes_item_sits_above_exit_on_the_arrow_menu(qapp, qtbot):
    cfg = AppConfig()
    cfg.settings.color_scheme = "bright"
    use("bright")
    trigger = TriggerWidget(cfg)
    qtbot.addWidget(trigger)
    trigger._show_context_menu(QPoint(8, 8))
    menu = _arrow_menu(trigger)
    qtbot.addWidget(menu)
    labels = [
        "---" if action.isSeparator() else action.text()
        for action in menu.actions()
        if action.isSeparator() or action.text()
    ]
    assert labels[-8:] == [
        "---",
        "Opacity",
        "Decay rate",
        "---",
        "Color Schemes",
        "---",
        "Help",
        "Exit",
    ]
    scheme_action = next(action for action in menu.actions() if action.text() == "Color Schemes")
    choices = scheme_action.menu().actions()
    assert [action.text() for action in choices] == ["Dark", "Medium", "Bright"]
    assert [action.isChecked() for action in choices] == [False, False, True]
    menu.close()


def test_picking_a_scheme_restyles_open_lists_and_does_not_reopen(qapp, qtbot, monkeypatch):
    cfg = AppConfig()
    trigger = TriggerWidget(cfg)
    qtbot.addWidget(trigger)
    trigger.resize(80, 48)
    trigger.move(200, 200)
    trigger.show()
    panel = DropdownPanel(cfg)
    qtbot.addWidget(panel)
    panel.rebuild_buttons([Launcher.new("Calc", "calc")])
    assert "rgba(35, 35, 38, 245)" in panel._frame.styleSheet()
    assert "rgba(255, 220, 70, 240)" in panel._buttons[0].styleSheet()

    seen = []

    def _apply(scheme_id: str) -> None:
        seen.append(scheme_id)
        use(scheme_id)
        cfg.settings.color_scheme = scheme_id
        panel.apply_theme()
        trigger.update()

    trigger.color_scheme_selected.connect(_apply)
    trigger._show_context_menu(QPoint(8, 8))
    qapp.processEvents()
    menu = _arrow_menu(trigger)
    inside = menu.frameGeometry().center()
    monkeypatch.setattr("runner.ui.trigger.QCursor.pos", lambda: inside)
    next(action for action in menu.actions() if action.text() == "Color Schemes").menu().actions()[2].trigger()
    menu.close()
    qapp.processEvents()

    assert seen == ["bright"]
    assert menu.isVisible() is False
    assert trigger._in_context_menu is False
    assert "rgba(228, 204, 160, 248)" in panel._frame.styleSheet()
    assert "rgba(176, 96, 24, 255)" in panel._buttons[0].styleSheet()
    assert "rgba(255, 220, 70, 240)" not in panel._buttons[0].styleSheet()

    use("medium")
    panel.apply_theme()
    trigger.update()
    assert "rgba(78, 82, 94, 242)" in panel._frame.styleSheet()
    assert "rgba(212, 176, 96, 245)" in panel._buttons[0].styleSheet()
    image = trigger.grab().toImage()
    # The medium arrow is a mid slate, not the dark scheme's near-black pill.
    fill = image.pixelColor(image.width() // 2, image.height() // 2)
    assert fill.alpha() > 0
    assert fill.red() > 60
    assert abs(fill.red() - QColor(30, 30, 30).red()) > 20
