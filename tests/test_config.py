"""Basic non-GUI tests for config persistence and Launcher model."""

import json
import tempfile
from pathlib import Path

import pytest

from runner.config import AppConfig, ConfigManager, Launcher, Settings


def test_launcher_new_and_fields():
    l = Launcher.new(name="Test", command="calc", args="--foo", enabled=True, run_as_admin=True)
    assert l.id
    assert l.name == "Test"
    assert l.command == "calc"
    assert l.args == "--foo"
    assert l.enabled is True
    assert l.run_as_admin is True
    assert l.show_console is False
    assert l.working_dir is None


def test_appconfig_roundtrip():
    cfg = AppConfig()
    l1 = Launcher.new("One", "notepad")
    l2 = Launcher.new("Two", "https://example.com", working_dir="/tmp")
    cfg.launchers = [l1, l2]
    cfg.settings.dropdown_width = 300
    cfg.settings.pinned_open = True

    d = cfg.to_dict()
    assert d["version"] == 1
    assert len(d["launchers"]) == 2
    assert d["settings"]["pinned_open"] is True
    assert d["settings"]["dropdown_width"] == 300

    cfg2 = AppConfig.from_dict(d)
    assert len(cfg2.launchers) == 2
    assert cfg2.launchers[1].working_dir == "/tmp"
    assert cfg2.settings.pinned_open is True


def test_configmanager_save_load(tmp_path, monkeypatch):
    # Redirect config dir to temp for test
    test_dir = tmp_path / "RunnerTest"
    monkeypatch.setattr(
        "runner.config.platformdirs.user_config_dir",
        lambda *a, **k: str(test_dir)
    )

    mgr = ConfigManager()
    # first load creates default
    c = mgr.config
    assert isinstance(c, AppConfig)
    assert c.launchers == []

    # add one
    l = Launcher.new("Calc", "calc")
    mgr.add_launcher(l)
    assert len(mgr.config.launchers) == 1

    # path should exist
    assert mgr.config_path.exists()

    # reload fresh
    mgr2 = ConfigManager()
    assert len(mgr2.config.launchers) == 1
    assert mgr2.config.launchers[0].name == "Calc"

    # update settings
    mgr.update_settings(dropdown_width=250, pinned_open=True)
    assert mgr.config.settings.dropdown_width == 250

    # remove
    mgr.remove_launcher(l.id)
    assert len(mgr.config.launchers) == 0


def test_reorder():
    mgr = ConfigManager()
    a = Launcher.new("A", "a")
    b = Launcher.new("B", "b")
    c = Launcher.new("C", "c")
    mgr.config.launchers = [a, b, c]
    mgr.reorder_launchers([c.id, a.id, b.id])
    names = [l.name for l in mgr.config.launchers]
    assert names == ["C", "A", "B"]


# --- show_filter_box + pinned_open + defaults / migration (post BETA toggle feature) ---

def test_settings_defaults_include_filter_box_and_pinned():
    s = Settings()
    assert s.show_filter_box is True  # default so existing users see the box
    assert s.pinned_open is False


def test_appconfig_show_filter_box_roundtrip():
    cfg = AppConfig()
    cfg.settings.show_filter_box = False
    cfg.settings.pinned_open = True
    d = cfg.to_dict()
    assert d["settings"]["show_filter_box"] is False
    assert d["settings"]["pinned_open"] is True

    cfg2 = AppConfig.from_dict(d)
    assert cfg2.settings.show_filter_box is False
    assert cfg2.settings.pinned_open is True


def test_old_config_without_show_filter_box_defaults_true():
    """Old persisted configs (pre filter toggle) should default the new field to True."""
    old = {
        "version": 1,
        "launchers": [],
        "settings": {
            "dropdown_width": 280,
            "trigger_width": 36,
            "trigger_height": 36,
            "animation_duration_ms": 120,
            "pinned_open": False,
            "position_x": 100,
            "position_y": 100,
            # deliberately no "show_filter_box"
        },
    }
    cfg = AppConfig.from_dict(old)
    assert cfg.settings.show_filter_box is True  # graceful default


def test_configmanager_update_settings_for_filter_and_pin(tmp_path, monkeypatch):
    test_dir = tmp_path / "RunnerTestFilter"
    monkeypatch.setattr(
        "runner.config.platformdirs.user_config_dir",
        lambda *a, **k: str(test_dir)
    )
    mgr = ConfigManager()
    c = mgr.config
    c.launchers.clear()
    mgr.save(c)

    mgr.update_settings(show_filter_box=False, pinned_open=True)
    assert mgr.config.settings.show_filter_box is False
    assert mgr.config.settings.pinned_open is True

    # persist + reload
    mgr2 = ConfigManager()
    assert mgr2.config.settings.show_filter_box is False
    assert mgr2.config.settings.pinned_open is True
