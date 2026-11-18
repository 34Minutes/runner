"""Opacity: the arrow-menu slider, and the box alpha kept in the config."""

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QMenu, QWidgetAction

from runner.config import AppConfig, ConfigManager
from runner.ui.theme import DARK, use, with_opacity
from runner.ui.trigger import TriggerWidget


def _arrow_menu(trigger):
    found = [
        menu
        for menu in trigger.findChildren(QMenu)
        if any(action.text() == "Exit" for action in menu.actions())
    ]
    assert found
    return found[-1]


def _box_color(trigger) -> QColor:
    image = trigger.grab().toImage()
    # Left interior of the pill, clear of the centered chevron.
    return image.pixelColor(max(1, image.width() // 8), image.height() // 2)


def test_stored_percent_replaces_scheme_alpha_and_negative_keeps_it():
    assert with_opacity((30, 30, 30, 170), -1) == (30, 30, 30, 170)
    assert with_opacity((30, 30, 30, 170), 0) == (30, 30, 30, 0)
    assert with_opacity((30, 30, 30, 170), 100) == (30, 30, 30, 255)
    assert with_opacity((30, 30, 30, 170), 50)[3] == round(50 * 255 / 100)
    assert with_opacity((30, 30, 30, 170), 140)[3] == 255


def test_old_config_keeps_scheme_opacity_until_a_slider_is_saved(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "runner.config.platformdirs.user_config_dir",
        lambda *args, **kwargs: str(tmp_path),
    )
    loaded = AppConfig.from_dict(
        {"version": 1, "settings": {"color_scheme": "bright"}, "launchers": []}
    )
    assert loaded.settings.box_opacity == -1
    kept = AppConfig.from_dict(
        {"version": 1, "settings": {"box_opacity": 40, "arrow_opacity": 10}, "launchers": []}
    )
    assert kept.settings.box_opacity == 40
    assert not hasattr(kept.settings, "arrow_opacity")

    mgr = ConfigManager()
    assert mgr.config.settings.box_opacity == -1
    mgr.update_settings(box_opacity=25)
    again = ConfigManager()
    assert again.config.settings.box_opacity == 25


def test_arrow_menu_has_one_opacity_row_the_slider(qapp, qtbot):
    use("dark")
    cfg = AppConfig()
    trigger = TriggerWidget(cfg)
    qtbot.addWidget(trigger)
    trigger._show_context_menu(QPoint(8, 8))
    qapp.processEvents()
    menu = _arrow_menu(trigger)
    qtbot.addWidget(menu)

    opacity_rows = [action for action in menu.actions() if action.text() == "Opacity"]
    assert len(opacity_rows) == 1
    assert isinstance(opacity_rows[0], QWidgetAction)
    menu.close()
    qapp.processEvents()
    assert trigger.findChildren(QDialog, "opacityDialog") == []


def test_saved_box_opacity_still_paints_the_box(qapp, qtbot):
    use("dark")
    cfg = AppConfig()
    trigger = TriggerWidget(cfg)
    qtbot.addWidget(trigger)
    trigger.resize(120, 96)
    rested = _box_color(trigger)
    assert abs(rested.alpha() - DARK.trigger_fill[3]) <= 2

    cfg.settings.box_opacity = 100
    assert _box_color(trigger).alpha() > 250
