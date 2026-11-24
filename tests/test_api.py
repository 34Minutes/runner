"""Changing launchers, groups and containers from outside Runner: runner.api and `runner ctl`."""

import json
import subprocess
import sys
import threading
import time
import uuid

import pytest
from PySide6.QtWidgets import QApplication

from runner import ctl
from runner import main as main_mod
from runner.api import RunnerApi
from runner.config import ConfigManager, Group, GroupMember, Launcher


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr("runner.config.platformdirs.user_config_dir", lambda *a, **k: str(tmp_path))
    manager = ConfigManager()
    manager.config.launchers = [Launcher.new("Mine by hand", "calc")]
    manager.save()
    return manager


def _ok(api, request):
    reply = api.handle(request)
    assert reply["ok"], reply
    return reply["result"]


def _refused(api, request) -> str:
    reply = api.handle(request)
    assert not reply["ok"], reply
    return reply["error"]


# ------------------------------------------------------------------ the rules


def test_a_launcher_and_group_can_be_made_listed_and_saved(cfg):
    api = RunnerApi(cfg)
    launcher = _ok(api, {"op": "launcher.add", "source": "claude", "data": {
        "name": "Build & deploy", "command": "./scripts/build-mac.sh", "args": "--deploy",
        "working_dir": "~/Projects/runner"}})
    assert launcher["source"] == "claude" and launcher["run_as_admin"] is False
    group = _ok(api, {"op": "group.add", "source": "claude", "data": {
        "name": "Release", "launchers": ["build & DEPLOY", {"ref": "Mine by hand", "concurrent": True}]}})
    assert [(m["name"], m["concurrent"]) for m in group["launchers"]] == [
        ("Build & deploy", False), ("Mine by hand", True)]

    again = ConfigManager()  # what is on disk
    assert [l.name for l in again.config.launchers] == ["Mine by hand", "Build & deploy"]
    assert again.config.groups[0].source == "claude"
    mine = _ok(api, {"op": "launcher.list", "filter": {"source": "claude"}})
    assert [l["name"] for l in mine] == ["Build & deploy"]
    assert mine[0]["groups"] == ["Release"]


def test_only_the_source_that_made_something_can_change_it(cfg):
    api = RunnerApi(cfg)
    _ok(api, {"op": "launcher.add", "source": "claude", "data": {"name": "Tool", "command": "tool"}})
    assert "belongs to 'claude'" in _refused(api, {
        "op": "launcher.update", "source": "other", "ref": "Tool", "data": {"command": "evil"}})
    assert "made in Runner" in _refused(api, {
        "op": "launcher.delete", "source": "claude", "ref": "Mine by hand"})
    assert "needs a source" in _refused(api, {"op": "launcher.add", "data": {"name": "x", "command": "y"}})
    _ok(api, {"op": "launcher.delete", "source": "claude", "ref": "Tool"})
    assert [l.name for l in cfg.config.launchers] == ["Mine by hand"]


def test_upsert_changes_the_one_it_made_instead_of_adding_another(cfg):
    api = RunnerApi(cfg)
    request = {"op": "launcher.upsert", "source": "claude", "data": {"name": "Tool", "command": "v1"}}
    first = _ok(api, request)
    request["data"]["command"] = "v2"
    second = _ok(api, request)
    assert first["id"] == second["id"] and second["command"] == "v2"
    assert len(cfg.config.launchers) == 2


def test_nothing_from_outside_runs_as_admin_or_switches_a_schedule_on(cfg):
    api = RunnerApi(cfg)
    assert "run_as_admin" in _refused(api, {"op": "launcher.add", "source": "c", "data": {
        "name": "x", "command": "y", "run_as_admin": True}})
    assert "Only you can turn" in _refused(api, {"op": "group.add", "source": "c", "data": {
        "name": "G", "scheduled": True}})
    group = _ok(api, {"op": "group.add", "source": "c", "data": {
        "name": "G", "schedule": [{"start": "2026-12-01T09:00", "weeks": 1}]}})
    assert group["scheduled"] is False and group["schedule"] == [{"start": "2026-12-01T09:00", "weeks": 1}]
    assert "0 to 3" in _refused(api, {"op": "group.update", "source": "c", "ref": "G", "data": {
        "schedule": [{"start": "2026-12-01T09:00", "weeks": 5}]}})
    assert not any(hasattr(RunnerApi, name) for name in ("run", "_run", "launch"))


def test_a_scheduled_group_and_its_launchers_commands_are_locked(cfg):
    api = RunnerApi(cfg)
    _ok(api, {"op": "launcher.add", "source": "c", "data": {"name": "Job", "command": "job"}})
    _ok(api, {"op": "group.add", "source": "c", "data": {"name": "Nightly", "launchers": ["Job"]}})
    cfg.config.groups[0].scheduled = True  # the user switched it on in Runner
    assert "Turn its Schedule switch off" in _refused(api, {
        "op": "group.update", "source": "c", "ref": "Nightly", "data": {"launchers": []}})
    assert "runs on a schedule (Nightly)" in _refused(api, {
        "op": "launcher.update", "source": "c", "ref": "Job", "data": {"command": "other"}})
    _ok(api, {"op": "launcher.update", "source": "c", "ref": "Job", "data": {"name": "Job 2"}})


def test_bad_requests_are_explained(cfg):
    api = RunnerApi(cfg)
    assert "Unknown op" in _refused(api, {"op": "launcher.run", "source": "c"})
    assert "no field 'colour'" in _refused(api, {"op": "launcher.add", "source": "c", "data": {
        "name": "x", "command": "y", "colour": "red"}})
    assert "wrong type" in _refused(api, {"op": "launcher.add", "source": "c", "data": {
        "name": "x", "command": 5}})
    assert "No launcher" in _refused(api, {"op": "group.add", "source": "c", "data": {
        "name": "G", "launchers": ["missing"]}})
    cfg.config.launchers.append(Launcher.new("Twin", "a"))
    cfg.config.launchers.append(Launcher.new("twin", "b"))
    assert "2 launchers are named 'Twin'" in _refused(api, {"op": "launcher.get", "ref": "Twin"})


def test_containers_list_launchers(cfg):
    api = RunnerApi(cfg)
    box = _ok(api, {"op": "container.add", "source": "c", "data": {"name": "Box", "launchers": ["Mine by hand"]}})
    assert [m["name"] for m in box["launchers"]] == ["Mine by hand"]
    assert "concurrent is for groups" in _refused(api, {"op": "container.update", "source": "c", "ref": "Box",
        "data": {"launchers": [{"ref": "Mine by hand", "concurrent": True}]}})


# ------------------------------------------------------------------ the command line


def _request(*argv):
    args = ctl.build_parser().parse_args(list(argv))
    return ctl.request_for(args, list(argv))


def test_the_command_line_builds_requests():
    assert _request("--as", "claude", "launcher", "add", "--name", "B", "--command", "./b.sh",
                    "--args=--deploy", "--cwd", "~/p", "--no-show-in-main") == {
        "op": "launcher.add", "source": "claude", "data": {
            "name": "B", "command": "./b.sh", "args": "--deploy", "working_dir": "~/p", "show_in_main": False}}
    request = _request("group", "upsert", "--name", "R", "--launcher", "A", "--concurrent", "B",
                       "--date", "2026-12-01 09:00", "--every", "1 week", "--date", "2026-12-02 10:30",
                       "--click-runs")
    assert request["source"] == "cli"
    assert request["data"] == {
        "name": "R",
        "launchers": [{"ref": "A", "concurrent": False}, {"ref": "B", "concurrent": True}],
        "click_runs": True,
        "schedule": [{"start": "2026-12-01T09:00", "weeks": 1}, {"start": "2026-12-02T10:30"}],
    }
    assert _request("--as", "x", "group", "list", "--mine") == {"op": "group.list", "filter": {"source": "x"}}
    assert _request("container", "list", "--source", "y") == {"op": "container.list", "filter": {"source": "y"}}


def test_intervals_read_like_people_write_them():
    assert ctl.parse_every("1 week") == {"weeks": 1}
    assert ctl.parse_every("1d 12h") == {"days": 1, "hours": 12}
    assert ctl.parse_every("2 months, 30 mins") == {"months": 2, "minutes": 30}
    with pytest.raises(ValueError):
        ctl.parse_every("fortnightly")


# ------------------------------------------------------------------ through the socket


def test_a_request_goes_through_the_socket_and_a_plain_message_still_shows(qapp, cfg, monkeypatch):
    name = f"RunnerTest_{uuid.uuid4().hex[:10]}"
    monkeypatch.setattr(main_mod, "SINGLE_INSTANCE_SERVER", name)
    monkeypatch.setattr(ctl, "SINGLE_INSTANCE_SERVER", name)
    shown = []
    api = RunnerApi(cfg)
    server = main_mod._listen_for_other_copies(lambda: shown.append(True), api.handle)
    try:
        # `runner ctl` is its own process, as it is in real use.
        code = (
            # If it can't connect it must not fall back to the real config file.
            f"import runner.config as rc; rc.platformdirs.user_config_dir = lambda *a, **k: {str(cfg.config_dir)!r}; "
            f"import json, runner.ctl as c; c.SINGLE_INSTANCE_SERVER = {name!r}; "
            "print(json.dumps(c.send({'op': 'launcher.add', 'source': 'claude', "
            "'data': {'name': 'Via socket', 'command': 'x'}})))"
        )
        client = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 20
        while client.poll() is None and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.005)
        reply, live = json.loads(client.communicate(timeout=5)[0])
        assert live and reply["ok"] and reply["result"]["name"] == "Via socket"
        assert cfg.config.launchers[-1].source == "claude"

        thread = threading.Thread(target=main_mod._signal_running_copy)
        thread.start()
        for _ in range(200):
            QApplication.processEvents()
            thread.join(0.01)
            if shown:
                break
        assert shown == [True]
    finally:
        server.close()


def test_with_runner_closed_the_config_file_is_changed_directly(cfg, monkeypatch, capsys):
    monkeypatch.setattr(ctl, "SINGLE_INSTANCE_SERVER", f"RunnerTest_{uuid.uuid4().hex[:10]}")
    code = ctl.main(["--as", "claude", "--json", "launcher", "add", "--name", "Offline", "--command", "o"])
    out = capsys.readouterr()
    assert code == 0 and "isn't running" in out.err
    assert json.loads(out.out)["result"]["name"] == "Offline"
    assert ConfigManager().config.launchers[-1].name == "Offline"
    assert ctl.main(["ping"]) == ctl.EXIT_REFUSED


def test_the_app_refuses_changes_while_a_dialog_is_open(qapp, cfg, monkeypatch):
    from unittest.mock import MagicMock

    from runner.controller import RunnerController

    monkeypatch.setattr("runner.controller.create_tray", lambda **_: MagicMock())
    controller = RunnerController(qapp, cfg)
    try:
        add = {"op": "group.add", "source": "c", "data": {"name": "G", "launchers": ["Mine by hand"]}}
        monkeypatch.setattr(QApplication, "activeModalWidget", staticmethod(lambda: object()))
        assert "window open" in controller.answer_outside_request(add)["error"]
        assert controller.answer_outside_request({"op": "group.list"})["ok"]
        monkeypatch.setattr(QApplication, "activeModalWidget", staticmethod(lambda: None))
        assert controller.answer_outside_request(add)["ok"]
        assert [g.name for g in controller._execute_groups()] == ["G"]
    finally:
        controller.scheduler.stop()
        controller.trigger.hide()
        for panel in controller._all_lists():
            panel.force_hide()


def test_old_groups_and_launchers_load_without_a_source(cfg):
    group = Group.new("Old", [GroupMember(cfg.config.launchers[0].id)])
    cfg.config.groups = [group]
    cfg.save()
    raw = json.loads(cfg.config_path.read_text())
    for item in raw["launchers"] + raw["groups"]:
        item.pop("source")
    cfg.config_path.write_text(json.dumps(raw))
    loaded = ConfigManager().config
    assert loaded.launchers[0].source is None and loaded.groups[0].source is None


def test_the_guide_ships_with_the_package_and_covers_every_option(capsys):
    assert ctl.main(["guide"]) == 0
    text = capsys.readouterr().out
    assert text.startswith("# runner ctl: a guide for LLMs and scripts")
    parser = ctl.build_parser()
    for argv in (["launcher", "add"], ["group", "add"], ["container", "add"]):
        sub = parser
        for word in argv:
            sub = next(a for a in sub._actions if isinstance(a, ctl.argparse._SubParsersAction)).choices[word]
        for action in sub._actions:
            for option in action.option_strings:
                if option.startswith("--") and option not in ("--help", "--as", "--json"):
                    assert option.lstrip("-").removeprefix("no-") in text, f"{option} is not in the guide"


def test_as_and_json_work_after_the_command_too():
    late = ctl.build_parser().parse_args(["launcher", "list", "--mine", "--as", "claude", "--json"])
    early = ctl.build_parser().parse_args(["--as", "claude", "--json", "launcher", "list", "--mine"])
    plain = ctl.build_parser().parse_args(["launcher", "list"])
    assert (late.source, late.json) == (early.source, early.json) == ("claude", True)
    assert (plain.source, plain.json) == ("cli", False)
