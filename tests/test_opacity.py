"""Arrow-menu Opacity: a slider for the rounded box."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QLabel, QMenu, QSlider

from runner.config import AppConfig, ConfigManager
from runner.ui.theme import BRIGHT, DARK, opacity_percent, use, with_opacity
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
    assert opacity_percent((30, 30, 30, 170), -1) == round(170 * 100 / 255)
    assert opacity_percent((30, 30, 30, 170), 40) == 40
    assert opacity_percent((30, 30, 30, 170), 140) == 100


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


def test_opacity_item_opens_a_box_rule(qapp, qtbot, monkeypatch):
    use("dark")
    cfg = AppConfig()
    trigger = TriggerWidget(cfg)
    qtbot.addWidget(trigger)
    trigger.resize(120, 96)
    trigger.move(80, 80)
    trigger.show()
    saved = []
    trigger.opacity_changed.connect(saved.append)

    trigger._show_context_menu(QPoint(8, 8))
    qapp.processEvents()
    menu = _arrow_menu(trigger)
    qtbot.addWidget(menu)
    inside = menu.frameGeometry().center()
    monkeypatch.setattr("runner.ui.trigger.QCursor.pos", lambda: inside)
    labeled = [item for item in menu.actions() if item.text()]
    scheme_at = next(index for index, item in enumerate(labeled) if item.text() == "Color Schemes")
    action = labeled[scheme_at + 1]
    assert action.text() == "Opacity"
    assert action.menu() is None
    assert labeled[scheme_at].menu() is not None

    action.trigger()
    menu.close()
    qapp.processEvents()

    assert menu.isVisible() is False
    assert trigger._in_context_menu is False
    dialog = trigger.findChild(QDialog, "opacityDialog")
    assert dialog is not None
    assert dialog.isVisible()
    assert dialog.windowTitle() == "Opacity"
    assert dialog.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert dialog.x() >= trigger.mapToGlobal(QPoint(trigger.width(), 0)).x()

    box = dialog.findChild(QSlider, "boxOpacity")
    assert dialog.findChild(QSlider, "arrowOpacity") is None
    assert box.orientation() == Qt.Orientation.Horizontal
    assert box.value() == opacity_percent(DARK.trigger_fill, -1)
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert "Box" in labels
    assert "Arrow" not in labels
    assert dialog.findChild(QLabel, "boxOpacityReadout").text() == f"{box.value()}%"
    assert cfg.settings.box_opacity == -1
    assert saved == []

    rested = _box_color(trigger)
    assert abs(rested.alpha() - DARK.trigger_fill[3]) <= 2
    assert abs(rested.red() - DARK.trigger_fill[0]) <= 2

    action.trigger()
    qapp.processEvents()
    assert trigger.findChildren(QDialog, "opacityDialog") == [dialog]

    box.setValue(0)
    assert cfg.settings.box_opacity == 0
    assert saved == [0]
    assert _box_color(trigger).alpha() < 8

    box.setValue(100)
    solid = _box_color(trigger)
    assert solid.alpha() > 250
    assert abs(solid.red() - DARK.trigger_fill[0]) <= 2
    assert saved[-1] == 100

    dialog.close()
    qapp.processEvents()
    assert trigger._opacity_dialog is None


def test_untouched_box_rule_follows_a_scheme_change(qapp, qtbot):
    use("dark")
    cfg = AppConfig()
    trigger = TriggerWidget(cfg)
    qtbot.addWidget(trigger)
    trigger._show_context_menu(QPoint(8, 8))
    qapp.processEvents()
    menu = _arrow_menu(trigger)
    qtbot.addWidget(menu)
    labeled = [item for item in menu.actions() if item.text()]
    scheme_at = next(index for index, item in enumerate(labeled) if item.text() == "Color Schemes")
    labeled[scheme_at + 1].trigger()
    menu.close()
    qapp.processEvents()
    dialog = trigger.findChild(QDialog, "opacityDialog")
    box = dialog.findChild(QSlider, "boxOpacity")
    assert box.value() == opacity_percent(DARK.trigger_fill, -1)

    use("bright")
    trigger.color_scheme_selected.emit("bright")
    qapp.processEvents()
    assert box.value() == opacity_percent(BRIGHT.trigger_fill, -1)
    assert cfg.settings.box_opacity == -1

    box.setValue(10)
    use("dark")
    trigger.color_scheme_selected.emit("dark")
    qapp.processEvents()
    assert box.value() == 10
    assert cfg.settings.box_opacity == 10
