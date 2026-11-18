"""Opacity: the one slider on the arrow menu. The box takes its alpha from the scheme."""

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QMenu, QWidgetAction

from runner.config import AppConfig, ConfigManager
from runner.ui.theme import DARK, use
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


def test_old_box_opacity_key_is_ignored_and_dropped_on_save(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "runner.config.platformdirs.user_config_dir",
        lambda *args, **kwargs: str(tmp_path),
    )
    (tmp_path / "config.json").write_text(
        '{"version": 2, "settings": {"box_opacity": 40}, "launchers": []}'
    )
    mgr = ConfigManager()
    assert not hasattr(mgr.config.settings, "box_opacity")
    assert mgr.load_problems == []
    mgr.save()
    assert "box_opacity" not in (tmp_path / "config.json").read_text()


def test_box_uses_the_scheme_alpha(qapp, qtbot):
    use("dark")
    trigger = TriggerWidget(AppConfig())
    qtbot.addWidget(trigger)
    trigger.resize(120, 96)
    rested = _box_color(trigger)
    assert abs(rested.alpha() - DARK.trigger_fill[3]) <= 2
    assert abs(rested.red() - DARK.trigger_fill[0]) <= 2
