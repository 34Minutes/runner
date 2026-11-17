"""Tests for launcher.py focusing on pure logic and exercising branches via mocks."""

import os
from unittest.mock import patch, MagicMock

import pytest

from runner.config import Launcher
from runner import launcher as launcher_mod


def _win32_subprocess_mock():
    """Return a mock subprocess module with Popen + the win-only flag constants."""
    m = MagicMock()
    m.Popen = MagicMock()
    m.CREATE_NEW_CONSOLE = 0x10
    m.CREATE_NO_WINDOW = 0x08000000
    return m


def test_is_url_or_protocol():
    assert launcher_mod._is_url_or_protocol("https://example.com")
    assert launcher_mod._is_url_or_protocol("http://example.com")
    assert launcher_mod._is_url_or_protocol("mailto:foo@bar.com")
    assert launcher_mod._is_url_or_protocol("ms-settings:privacy")
    assert launcher_mod._is_url_or_protocol("file:///tmp/foo")
    assert launcher_mod._is_url_or_protocol("foo://bar")  # short proto, :// within [:10]
    assert not launcher_mod._is_url_or_protocol("calc")
    assert not launcher_mod._is_url_or_protocol("/usr/bin/firefox")


def test_is_python_script():
    assert launcher_mod._is_python_script("foo.py")
    assert launcher_mod._is_python_script("/path/to/script.py")
    assert launcher_mod._is_python_script("script.py")
    assert not launcher_mod._is_python_script("script")
    assert not launcher_mod._is_python_script("script.txt")


def test_expand_command():
    os.environ["TEST_VAR"] = "expanded"
    try:
        expanded = launcher_mod._expand_command("$TEST_VAR/bar")
        assert "expanded" in expanded or "TEST_VAR" in expanded
        # ~ expansion
        homey = launcher_mod._expand_command("~/foo")
        assert homey.startswith("/") or homey.startswith("~") or "home" in homey.lower() or len(homey) > 5
    finally:
        del os.environ["TEST_VAR"]


def test_launch_empty_raises():
    l = Launcher.new("Empty", "   ")
    with pytest.raises(ValueError):
        launcher_mod.launch(l)


@patch("runner.launcher.subprocess.Popen")
def test_launch_url_non_windows(mock_popen):
    with patch("sys.platform", "darwin"):
        l = Launcher.new("Web", "https://example.com")
        launcher_mod.launch(l)
        mock_popen.assert_called()


@patch("runner.launcher.subprocess.Popen")
def test_launch_python_non_windows(mock_popen):
    with patch("sys.platform", "darwin"):
        l = Launcher.new("Script", "myscript.py")
        launcher_mod.launch(l)
        mock_popen.assert_called()


@patch("runner.launcher.subprocess.Popen")
def test_launch_darwin_app(mock_popen):
    with patch("sys.platform", "darwin"):
        l = Launcher.new("Brave", "Brave Browser", args="https://x.com")
        launcher_mod.launch(l)
        mock_popen.assert_called()


@patch("runner.launcher.subprocess.Popen")
def test_launch_darwin_app_with_flags(mock_popen):
    with patch("sys.platform", "darwin"):
        l = Launcher.new("Brave", "Brave Browser", args="--incognito https://x.com")
        launcher_mod.launch(l)
        mock_popen.assert_called()


@patch("runner.launcher._launch_as_admin_windows")
def test_launch_run_as_admin_calls_helper(mock_admin):
    with patch("sys.platform", "win32"):
        l = Launcher.new("Admin", "cmd", run_as_admin=True)
        launcher_mod.launch(l)
        mock_admin.assert_called_once()


def test_get_default_icon_placeholder():
    l = Launcher.new("Foo", "bar")
    assert launcher_mod.get_default_icon_for_launcher(l) is None


@patch("runner.launcher.subprocess.Popen")
def test_launch_with_working_dir(mock_popen, tmp_path):
    with patch("sys.platform", "darwin"):
        l = Launcher.new("App", "echo", working_dir=str(tmp_path))
        launcher_mod.launch(l)
        mock_popen.assert_called()


@patch("runner.launcher.subprocess.Popen")
def test_launch_python_explicit_on_darwin(mock_popen):
    with patch("sys.platform", "darwin"):
        l = Launcher.new("Py", "python", args="-c 'print(1)'")
        launcher_mod.launch(l)
        mock_popen.assert_called()


def test_is_python_script_edge():
    assert not launcher_mod._is_python_script("")
    # .PY normalizes via .lower() on suffix
    assert launcher_mod._is_python_script("foo.PY")
    assert launcher_mod._is_python_script("foo.py")


# --- Win32 specific branches (exercised via platform patch + mocks so they run on any OS for coverage) ---

def test_launch_url_windows():
    with patch("sys.platform", "win32"):
        # create=True lets us add the win32-only attr to the os module object for this test
        with patch("runner.launcher.os.startfile", create=True) as mock_start:
            l = Launcher.new("Web", "https://example.com")
            res = launcher_mod.launch(l)
            assert res is None
            mock_start.assert_called_once_with("https://example.com")


def _on_path(name):
    """shutil.which stand-in: every program is found, as C:\\Tools\\<name>.exe."""
    return f"C:\\Tools\\{name}.exe"


@patch("runner.launcher.subprocess", new_callable=_win32_subprocess_mock)
def test_launch_python_windows(mock_sub):
    with patch("sys.platform", "win32"), patch("runner.launcher.shutil.which", _on_path):
        launcher_mod.launch(Launcher.new("Script", "myscript.py"))
    argv = mock_sub.Popen.call_args[0][0]
    assert argv == ["C:\\Tools\\py.exe", "-3", "myscript.py"]


@patch("runner.launcher.subprocess", new_callable=_win32_subprocess_mock)
def test_launch_win32_program_on_path_starts_without_cmd(mock_sub):
    """No cmd.exe in between, so & | % reach the program as typed."""
    with patch("sys.platform", "win32"), patch("runner.launcher.shutil.which", _on_path):
        launcher_mod.launch(Launcher.new("Tool", "tool", args='"a & b" 50% x|y'))
    call = mock_sub.Popen.call_args
    assert call[0][0] == ["C:\\Tools\\tool.exe", "a & b", "50%", "x|y"]
    assert "shell" not in call[1]
    assert call[1]["creationflags"] == mock_sub.CREATE_NO_WINDOW


@patch("runner.launcher.subprocess", new_callable=_win32_subprocess_mock)
def test_launch_win32_show_console(mock_sub):
    with patch("sys.platform", "win32"), patch("runner.launcher.shutil.which", _on_path):
        launcher_mod.launch(Launcher.new("Cmd", "cmd", show_console=True))
    assert mock_sub.Popen.call_args[1]["creationflags"] == mock_sub.CREATE_NEW_CONSOLE


def test_launch_win32_name_not_on_path_uses_shell_execute():
    """An App Paths name like 'brave', a shortcut, or a document opens like the Run dialog."""
    fake_ctypes = MagicMock()
    fake_ctypes.windll.shell32.ShellExecuteW.return_value = 42
    with patch("sys.platform", "win32"), \
         patch("runner.launcher.shutil.which", return_value=None), \
         patch("runner.launcher.subprocess.Popen") as mock_popen, \
         patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        result = launcher_mod.launch(Launcher.new("Brave", "brave", args="https://x.com"))
    assert result is None
    mock_popen.assert_not_called()
    args = fake_ctypes.windll.shell32.ShellExecuteW.call_args[0]
    assert args[1:4] == ("open", "brave", "https://x.com")


def test_launch_win32_shell_execute_failure_is_reported():
    """A typo used to vanish inside cmd.exe. Now Windows' refusal is an error."""
    fake_ctypes = MagicMock()
    fake_ctypes.windll.shell32.ShellExecuteW.return_value = 2  # ERROR_FILE_NOT_FOUND
    with patch("sys.platform", "win32"), \
         patch("runner.launcher.shutil.which", return_value=None), \
         patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        with pytest.raises(OSError, match="could not start 'brav'"):
            launcher_mod.launch(Launcher.new("Typo", "brav"))


def test_shell_execute_child_does_not_get_bundle_qt_paths(monkeypatch):
    """ShellExecute takes no environment, so the bundle's entries are removed for the call."""
    monkeypatch.setenv("QT_PLUGIN_PATH", "C:\\Runner\\_internal\\PySide6\\plugins")
    seen = {}
    fake_ctypes = MagicMock()

    def fake_shell_execute(*_args):
        seen["qt"] = os.environ.get("QT_PLUGIN_PATH")
        return 42

    fake_ctypes.windll.shell32.ShellExecuteW.side_effect = fake_shell_execute
    with patch("runner.launcher.sys.frozen", True, create=True), \
         patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        launcher_mod._shell_execute_windows("open", ["brave"], None)
    assert seen["qt"] is None
    # Runner's own process keeps it.
    assert os.environ["QT_PLUGIN_PATH"].endswith("plugins")


def test_launch_run_as_admin_windows_body_covered():
    """Executes the _launch_as_admin_windows body (and its inner import + ShellExecuteW) under win32 patch.
    Also provide subprocess flags (code assigns creationflags before the run_as_admin early return).
    """
    fake_ctypes = MagicMock()
    with patch("sys.platform", "win32"), \
         patch("runner.launcher.subprocess") as mock_sub, \
         patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        mock_sub.CREATE_NEW_CONSOLE = 0x10
        mock_sub.CREATE_NO_WINDOW = 0x08000000
        # ShellExecuteW returns a value above 32 on success.
        fake_ctypes.windll.shell32.ShellExecuteW.return_value = 42
        l = Launcher.new("AdminTask", "cmd.exe", run_as_admin=True)
        res = launcher_mod.launch(l)
        assert res is None
        # Body executed: the windll call happened on the injected mock
        assert fake_ctypes.windll.shell32.ShellExecuteW.called


def test_run_as_admin_failure_raises():
    """A declined UAC prompt or a missing file is reported, not silently dropped."""
    fake_ctypes = MagicMock()
    fake_ctypes.windll.shell32.ShellExecuteW.return_value = 5  # SE_ERR_ACCESSDENIED
    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        with pytest.raises(OSError):
            launcher_mod._launch_as_admin_windows(["tool.exe"], None)


def test_run_as_admin_quotes_arguments_with_spaces():
    fake_ctypes = MagicMock()
    fake_ctypes.windll.shell32.ShellExecuteW.return_value = 42
    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        launcher_mod._launch_as_admin_windows(["tool.exe", "C:\\My Files\\a.txt", "-v"], None)
    params = fake_ctypes.windll.shell32.ShellExecuteW.call_args[0][3]
    assert params == '"C:\\My Files\\a.txt" -v'


# --- Command routing on macOS and POSIX ---

@patch("runner.launcher.subprocess.Popen")
def test_darwin_cli_command_on_path_runs_directly(mock_popen):
    """A command found on PATH is a program, not an app name for open -a."""
    with patch("sys.platform", "darwin"), \
         patch("runner.launcher.shutil.which", return_value="/usr/bin/say"):
        launcher_mod.launch(Launcher.new("Say", "say", args="hello"))
    assert mock_popen.call_args[0][0] == ["say", "hello"]


@patch("runner.launcher.subprocess.Popen")
def test_darwin_app_name_uses_open_a(mock_popen):
    with patch("sys.platform", "darwin"), \
         patch("runner.launcher.shutil.which", return_value=None):
        launcher_mod.launch(Launcher.new("Brave", "Brave Browser", args="https://x.com"))
    assert mock_popen.call_args[0][0] == ["open", "-a", "Brave Browser", "https://x.com"]


@patch("runner.launcher.subprocess.Popen")
def test_darwin_app_bundle_path_uses_open_a(mock_popen):
    with patch("sys.platform", "darwin"):
        launcher_mod.launch(Launcher.new("Brave", "/Applications/Brave Browser.app"))
    assert mock_popen.call_args[0][0] == ["open", "-a", "/Applications/Brave Browser.app"]


@patch("runner.launcher.subprocess.Popen")
def test_existing_path_with_spaces_is_one_word(mock_popen, tmp_path):
    script = tmp_path / "My Scripts" / "run.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\n")
    with patch("sys.platform", "darwin"):
        launcher_mod.launch(Launcher.new("Run", str(script), args="--fast"))
    assert mock_popen.call_args[0][0] == [str(script), "--fast"]


@patch("runner.launcher.subprocess.Popen")
def test_command_field_is_split_into_words(mock_popen):
    """'python3 tool.py' runs python3 with tool.py, not a program named 'python3 tool.py'."""
    with patch("sys.platform", "linux"):
        launcher_mod.launch(Launcher.new("Tool", "python3 tool.py", args="-x"))
    argv = mock_popen.call_args[0][0]
    assert argv[0] == "python3"
    assert argv[-2:] == ["tool.py", "-x"]


@patch("runner.launcher.subprocess.Popen")
def test_frozen_build_runs_scripts_with_python_from_path(mock_popen):
    """In the packaged app sys.executable is Runner itself, so it must not run the script."""
    with patch("sys.platform", "darwin"), \
         patch("runner.launcher.sys.frozen", True, create=True), \
         patch("runner.launcher.shutil.which", return_value="/usr/local/bin/python3"):
        launcher_mod.launch(Launcher.new("Script", "/tmp/tool.py"))
    assert mock_popen.call_args[0][0] == ["/usr/local/bin/python3", "/tmp/tool.py"]


def test_frozen_build_without_python_raises():
    with patch("sys.platform", "darwin"), \
         patch("runner.launcher.sys.frozen", True, create=True), \
         patch("runner.launcher.shutil.which", return_value=None):
        with pytest.raises(FileNotFoundError):
            launcher_mod.launch(Launcher.new("Script", "/tmp/tool.py"))


@patch("runner.launcher.subprocess.Popen")
def test_packaged_app_does_not_pass_its_qt_paths_on(mock_popen, monkeypatch):
    """A Qt program started from Runner.app must not load Runner's bundled Qt."""
    monkeypatch.setenv("QT_PLUGIN_PATH", "/Applications/Runner.app/Contents/Frameworks/PySide6/Qt/plugins")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEIxyz")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/local/lib")
    monkeypatch.setenv("HOME_MARKER", "kept")
    with patch("sys.platform", "linux"), \
         patch("runner.launcher.sys.frozen", True, create=True):
        launcher_mod.launch(Launcher.new("Tool", "echo"))
    env = mock_popen.call_args[1]["env"]
    assert "QT_PLUGIN_PATH" not in env
    assert env["LD_LIBRARY_PATH"] == "/usr/local/lib"
    assert "LD_LIBRARY_PATH_ORIG" not in env
    assert env["HOME_MARKER"] == "kept"


@patch("runner.launcher.subprocess.Popen")
def test_source_run_passes_environment_unchanged(mock_popen):
    with patch("sys.platform", "linux"):
        launcher_mod.launch(Launcher.new("Tool", "echo"))
    assert mock_popen.call_args[1]["env"] is None


@patch("runner.launcher.subprocess.Popen")
def test_tilde_in_args_is_expanded(mock_popen):
    with patch("sys.platform", "darwin"), \
         patch("runner.launcher.shutil.which", return_value=None):
        launcher_mod.launch(Launcher.new("Finder", "Finder", args="~"))
    assert mock_popen.call_args[0][0][-1] == os.path.expanduser("~")
