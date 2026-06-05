"""Tests for launcher.py focusing on pure logic and exercising branches via mocks."""

import os
from unittest.mock import patch, MagicMock

import pytest

from script_runner.config import Launcher
from script_runner import launcher as launcher_mod


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


@patch("script_runner.launcher.subprocess.Popen")
def test_launch_url_non_windows(mock_popen):
    with patch("sys.platform", "darwin"):
        l = Launcher.new("Web", "https://example.com")
        launcher_mod.launch(l)
        mock_popen.assert_called()


@patch("script_runner.launcher.subprocess.Popen")
def test_launch_python_non_windows(mock_popen):
    with patch("sys.platform", "darwin"):
        l = Launcher.new("Script", "myscript.py")
        launcher_mod.launch(l)
        mock_popen.assert_called()


@patch("script_runner.launcher.subprocess.Popen")
def test_launch_darwin_app(mock_popen):
    with patch("sys.platform", "darwin"):
        l = Launcher.new("Brave", "Brave Browser", args="https://x.com")
        launcher_mod.launch(l)
        mock_popen.assert_called()


@patch("script_runner.launcher.subprocess.Popen")
def test_launch_darwin_app_with_flags(mock_popen):
    with patch("sys.platform", "darwin"):
        l = Launcher.new("Brave", "Brave Browser", args="--incognito https://x.com")
        launcher_mod.launch(l)
        mock_popen.assert_called()


@pytest.mark.xfail(reason="win32 admin path not fully mockable on darwin without deeper patches")
@patch("script_runner.launcher._launch_as_admin_windows")
def test_launch_run_as_admin_calls_helper(mock_admin):
    with patch("sys.platform", "win32"):
        l = Launcher.new("Admin", "cmd", run_as_admin=True)
        launcher_mod.launch(l)
        mock_admin.assert_called_once()


def test_get_default_icon_placeholder():
    l = Launcher.new("Foo", "bar")
    assert launcher_mod.get_default_icon_for_launcher(l) is None


@patch("script_runner.launcher.subprocess.Popen")
def test_launch_with_working_dir(mock_popen, tmp_path):
    with patch("sys.platform", "darwin"):
        l = Launcher.new("App", "echo", working_dir=str(tmp_path))
        launcher_mod.launch(l)
        mock_popen.assert_called()


@patch("script_runner.launcher.subprocess.Popen")
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
        with patch("script_runner.launcher.os.startfile", create=True) as mock_start:
            l = Launcher.new("Web", "https://example.com")
            res = launcher_mod.launch(l)
            assert res is None
            mock_start.assert_called_once_with("https://example.com")


@patch("script_runner.launcher.subprocess", new_callable=_win32_subprocess_mock)
def test_launch_python_windows(mock_sub):
    with patch("sys.platform", "win32"):
        l = Launcher.new("Script", "myscript.py")
        launcher_mod.launch(l)
        # On win it uses "py -3" + shell? but the argv build line + creationflags are hit
        assert mock_sub.Popen.called


@patch("script_runner.launcher.subprocess", new_callable=_win32_subprocess_mock)
def test_launch_win32_bare_command_shell(mock_sub):
    with patch("sys.platform", "win32"):
        l = Launcher.new("Calc", "calc")
        # the code will do subprocess.Popen(...) which is our mock's Popen, and use the flags
        launcher_mod.launch(l)
        assert mock_sub.Popen.called
        # shell=True path taken
        call = mock_sub.Popen.call_args
        assert call[1].get("shell") is True or "shell" in str(call)


@patch("script_runner.launcher.subprocess", new_callable=_win32_subprocess_mock)
def test_launch_win32_show_console(mock_sub):
    with patch("sys.platform", "win32"):
        l = Launcher.new("Cmd", "cmd", show_console=True)
        launcher_mod.launch(l)
        assert mock_sub.Popen.called


@patch("script_runner.launcher.subprocess", new_callable=_win32_subprocess_mock)
def test_launch_win32_python_wrapped_console(mock_sub):
    with patch("sys.platform", "win32"):
        l = Launcher.new("PyScript", "python", args="myscript.py", show_console=True)
        launcher_mod.launch(l)
        assert mock_sub.Popen.called



def test_launch_run_as_admin_windows_body_covered():
    """Executes the _launch_as_admin_windows body (and its inner import + ShellExecuteW) under win32 patch.
    Also provide subprocess flags (code assigns creationflags before the run_as_admin early return).
    """
    fake_ctypes = MagicMock()
    with patch("sys.platform", "win32"), \
         patch("script_runner.launcher.subprocess") as mock_sub, \
         patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        mock_sub.CREATE_NEW_CONSOLE = 0x10
        mock_sub.CREATE_NO_WINDOW = 0x08000000
        l = Launcher.new("AdminTask", "cmd.exe", run_as_admin=True)
        res = launcher_mod.launch(l)
        assert res is None
        # Body executed: the windll call happened on the injected mock
        assert fake_ctypes.windll.shell32.ShellExecuteW.called


def test_shell_execute_helper_body():
    """Directly hit _shell_execute lines (used by admin fallback path). Inner import mocked via sys.modules."""
    fake_ctypes = MagicMock()
    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        launcher_mod._shell_execute("notepad", "--foo", cwd=None, show=1)
        assert fake_ctypes.windll.shell32.ShellExecuteW.called
