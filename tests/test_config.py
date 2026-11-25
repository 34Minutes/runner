"""Basic non-GUI tests for config persistence and Launcher model."""

import json


from runner.config import AppConfig, ConfigManager, Launcher, Settings


def test_launcher_new_and_fields():
    l = Launcher.new(name="Test", command="calc", args="--foo", run_as_admin=True)
    assert l.id
    assert l.name == "Test"
    assert l.command == "calc"
    assert l.args == "--foo"
    assert l.show_in_main is True
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
    assert d["version"] == 2
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
    assert s.show_startup_greeting is True


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


# --- Validation: one bad entry must not wipe the whole config ---

def _isolated(tmp_path, monkeypatch, name="RunnerValidate"):
    test_dir = tmp_path / name
    monkeypatch.setattr(
        "runner.config.platformdirs.user_config_dir",
        lambda *a, **k: str(test_dir),
    )
    test_dir.mkdir(parents=True, exist_ok=True)
    return test_dir


def test_bad_entries_are_skipped_not_fatal():
    good = Launcher.new("Good", "calc")
    data = {
        "version": 1,
        "settings": {"pinned_open": "yes", "trigger_width": 150},
        "launchers": [
            {"id": good.id, "name": "Good", "command": "calc", "enabled": "false"},
            {"name": "No id", "command": "x"},
            "not an object",
            {"id": good.id, "name": "Duplicate", "command": "y"},
        ],
        "groups": [
            {"name": "No id group", "members": []},
            {"id": "g1", "members": [{"launcher_id": good.id}, {"concurrent": True}]},
        ],
        "container_groups": [{"id": "c1", "name": "Box", "members": "oops"}],
    }
    problems: list[str] = []
    cfg = AppConfig.from_dict(data, problems)

    assert [l.name for l in cfg.launchers] == ["Good"]
    # A wrong type falls back to the default instead of being truthy.
    assert cfg.launchers[0].show_in_main is True
    assert cfg.settings.pinned_open is False
    assert cfg.settings.trigger_width == 150
    assert [g.id for g in cfg.groups] == ["g1"]
    assert cfg.groups[0].name == ""
    assert [m.launcher_id for m in cfg.groups[0].members] == [good.id]
    assert cfg.container_groups[0].members == []
    assert len(problems) >= 6


def test_partially_bad_file_keeps_good_data_and_backs_up(tmp_path, monkeypatch):
    test_dir = _isolated(tmp_path, monkeypatch)
    good = Launcher.new("Keep me", "calc")
    (test_dir / "config.json").write_text(json.dumps({
        "version": 1,
        "launchers": [{"id": good.id, "name": "Keep me", "command": "calc"}, {"name": "broken"}],
        "groups": [{"members": []}],
    }))

    mgr = ConfigManager()
    assert [l.name for l in mgr.config.launchers] == ["Keep me"]
    assert mgr.had_saved_config is True
    assert mgr.load_problems
    backups = list(test_dir.glob("config.*.bak.json"))
    assert len(backups) == 1
    assert "broken" in backups[0].read_text()


def test_unreadable_file_is_moved_aside_and_reported(tmp_path, monkeypatch):
    test_dir = _isolated(tmp_path, monkeypatch, "RunnerCorrupt")
    (test_dir / "config.json").write_text("{ not json")

    mgr = ConfigManager()
    assert mgr.config.launchers == []
    assert mgr.had_saved_config is False
    assert len(mgr.load_problems) == 1
    backups = list(test_dir.glob("config.*.bak.json"))
    assert len(backups) == 1
    assert backups[0].read_text() == "{ not json"

    # A second corrupt file gets its own backup. The first is not overwritten.
    (test_dir / "config.json").write_text("[1, 2")
    _ = ConfigManager().config
    assert len(list(test_dir.glob("config.*.bak.json"))) == 2


def test_clean_file_reports_no_problems(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch, "RunnerClean")
    mgr = ConfigManager()
    mgr.add_launcher(Launcher.new("A", "a"))
    again = ConfigManager()
    assert again.config.launchers[0].name == "A"
    assert again.load_problems == []


def test_reload_updates_the_same_object(tmp_path, monkeypatch):
    """Widgets hold the AppConfig object. Reload must change it in place."""
    test_dir = _isolated(tmp_path, monkeypatch, "RunnerReload")
    mgr = ConfigManager()
    held = mgr.config
    held_launchers_before = held.launchers

    data = json.loads((test_dir / "config.json").read_text())
    data["settings"]["pinned_open"] = True
    data["settings"]["trigger_width"] = 222
    data["launchers"] = [{"id": "x1", "name": "Edited", "command": "calc"}]
    (test_dir / "config.json").write_text(json.dumps(data))

    returned = mgr.reload()
    assert returned is held
    assert mgr.config is held
    assert held.settings.pinned_open is True
    assert held.settings.trigger_width == 222
    assert [l.name for l in held.launchers] == ["Edited"]
    assert held_launchers_before is not held.launchers


def test_update_settings_can_defer_the_write(tmp_path, monkeypatch):
    """Sliders change settings on every tick and write the file once at the end."""
    test_dir = _isolated(tmp_path, monkeypatch, "RunnerDeferred")
    mgr = ConfigManager()
    _ = mgr.config  # creates the file
    before = (test_dir / "config.json").read_text()

    mgr.update_settings(save=False, opacity_percent=55)
    assert mgr.config.settings.opacity_percent == 55
    assert (test_dir / "config.json").read_text() == before

    mgr.save()
    assert ConfigManager().config.settings.opacity_percent == 55
