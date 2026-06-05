"""Basic non-GUI tests for config persistence and Launcher model."""

import json
import tempfile
from pathlib import Path

import pytest

from script_runner.config import AppConfig, ConfigManager, Launcher, Settings


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
    test_dir = tmp_path / "ScriptRunnerTest"
    monkeypatch.setattr(
        "script_runner.config.platformdirs.user_config_dir",
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
