"""Safety properties: where Runner starts, who can reach it, who can read its config."""

import os
import stat
import sys
from pathlib import Path

import pytest
from PySide6.QtNetwork import QLocalServer

from runner import main as main_mod
from runner.config import ConfigManager


def test_runner_works_from_the_home_folder(tmp_path, monkeypatch):
    # A bare program name must not be found in the folder Runner.exe sits in.
    monkeypatch.chdir(tmp_path)
    main_mod._start_in_home_folder()
    assert Path.cwd() == Path.home()


def test_main_moves_to_home_before_anything_else(qapp, monkeypatch):
    order = []
    monkeypatch.setattr(main_mod, "_start_in_home_folder", lambda: order.append("home"))

    def stop(*args, **kwargs):
        order.append("qt")
        raise SystemExit

    monkeypatch.setattr(main_mod, "QApplication", stop)
    with pytest.raises(SystemExit):
        main_mod.main()
    assert order == ["home", "qt"]


def test_single_instance_name_is_per_user(monkeypatch):
    import getpass

    monkeypatch.setattr(getpass, "getuser", lambda: "alice")
    alice = main_mod._single_instance_name()
    monkeypatch.setattr(getpass, "getuser", lambda: "bob")
    bob = main_mod._single_instance_name()
    assert alice != bob
    assert "alice" not in alice


def test_linux_socket_lives_in_the_private_runtime_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert Path(main_mod._single_instance_name()).parent == tmp_path
    # No runtime folder: fall back to a plain name.
    monkeypatch.delenv("XDG_RUNTIME_DIR")
    assert os.sep not in main_mod._single_instance_name()


def test_single_instance_server_is_owner_only(qapp, monkeypatch):
    created = []
    real = QLocalServer

    class Recording(real):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

        def listen(self, name):
            return True  # never touch the real socket

    monkeypatch.setattr(main_mod, "QLocalServer", Recording)
    main_mod._listen_for_other_copies(lambda: None)
    assert created[0].socketOptions() & QLocalServer.SocketOption.UserAccessOption


@pytest.mark.skipif(sys.platform == "win32", reason="Windows keeps %APPDATA% private itself")
def test_config_file_folder_and_backups_are_private(tmp_path, monkeypatch):
    folder = tmp_path / "Runner"
    folder.mkdir(mode=0o755)
    monkeypatch.setattr(
        "runner.config.platformdirs.user_config_dir", lambda *a, **k: str(folder)
    )
    old_umask = os.umask(0o022)
    try:
        mgr = ConfigManager()
        mgr.save()
        backup = mgr._backup(move=False)
    finally:
        os.umask(old_umask)
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert stat.S_IMODE(mgr.config_path.stat().st_mode) == 0o600
    assert backup is not None and stat.S_IMODE(backup.stat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="Windows keeps %APPDATA% private itself")
def test_an_old_readable_config_becomes_private_on_save(tmp_path, monkeypatch):
    folder = tmp_path / "Runner"
    folder.mkdir()
    monkeypatch.setattr(
        "runner.config.platformdirs.user_config_dir", lambda *a, **k: str(folder)
    )
    path = folder / "config.json"
    path.write_text('{"version": 2, "launchers": []}')
    path.chmod(0o644)
    mgr = ConfigManager()
    mgr.save()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
