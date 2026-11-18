"""Main entry point for Runner.

Starts Qt, makes sure only one copy runs, loads the config, and hands the
windows to RunnerController.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .config import ConfigManager, Launcher
from .controller import RunnerController
from .ui.theme import use

if sys.platform == "win32":
    from .utils import windows as win_utils  # type: ignore
else:
    win_utils = None  # type: ignore

SINGLE_INSTANCE_SERVER = "Runner_SingleInstance_v1"


def seed_test_data_if_needed(cfg: ConfigManager) -> None:
    """Add sample launchers on first run (calculator, calendar, web browser, ...)."""
    if cfg.config.launchers:
        return

    if sys.platform == "darwin":
        seeds: list[Launcher] = [
            Launcher.new(name="Calculator", command="Calculator"),
            Launcher.new(name="Calendar", command="Calendar"),
            Launcher.new(name="Web Browser", command="https://www.google.com"),
            Launcher.new(name="TextEdit", command="TextEdit"),
            Launcher.new(name="Finder", command="Finder", args="~"),
            Launcher.new(name="Terminal", command="Terminal"),
        ]
    else:
        seeds = [
            Launcher.new(name="Calculator", command="calc"),
            # Windows Calendar app via protocol.
            Launcher.new(name="Calendar", command="ms-calendar:"),
            Launcher.new(name="Web Browser", command="https://www.google.com"),
            Launcher.new(name="Notepad", command="notepad"),
            Launcher.new(name="File Explorer", command="explorer", args="."),
            Launcher.new(name="Command Prompt", command="cmd"),
        ]

    for seed in seeds:
        cfg.add_launcher(seed)


def _signal_running_copy() -> bool:
    """Ask a copy that is already running to show itself. True when one answered."""
    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_SERVER)
    if not socket.waitForConnected(300):
        return False
    socket.write(b"show")
    socket.waitForBytesWritten(300)
    socket.close()
    return True


def _listen_for_other_copies(on_show: Callable[[], None]) -> QLocalServer:
    """Any later copy connects here. Any message means 'show yourself'."""
    server = QLocalServer()
    # Remove a stale socket file left by a crash (common on macOS).
    QLocalServer.removeServer(SINGLE_INSTANCE_SERVER)
    if not server.listen(SINGLE_INSTANCE_SERVER):
        print(
            f"Runner: single-instance server did not start: {server.errorString()}",
            file=sys.stderr,
        )

    def on_new_connection() -> None:
        while server.hasPendingConnections():
            client = server.nextPendingConnection()
            client.readAll()
            client.close()
            on_show()

    server.newConnection.connect(on_new_connection)
    return server


def _test_quit_ms(argv: list[str]) -> int:
    """`runner --test-quit-after 1500` quits on its own, for automated runs."""
    if "--test-quit-after" not in argv:
        return 0
    try:
        return int(argv[argv.index("--test-quit-after") + 1])
    except (IndexError, ValueError):
        return 1500


def main() -> int:
    app = QApplication(sys.argv)

    # Windows: a named mutex is reliable even across elevation differences.
    if sys.platform == "win32" and win_utils is not None:
        if not win_utils.acquire_single_instance_mutex():
            _signal_running_copy()
            return 0
    if _signal_running_copy():
        return 0

    controller: RunnerController | None = None

    def show_running_copy() -> None:
        if controller is not None:
            controller.bring_forward()

    server = _listen_for_other_copies(show_running_copy)
    app._local_server = server  # keep the server alive with the app

    app.setApplicationName("Runner")
    # The arrow and the tray keep running with no regular window open.
    # Runner deliberately has no hidden main window: on macOS a hidden main
    # window plus frameless Tool windows and dialogs can trip AppKit asserts.
    app.setQuitOnLastWindowClosed(False)

    test_quit_ms = _test_quit_ms(sys.argv)
    if test_quit_ms > 0:
        QTimer.singleShot(test_quit_ms, app.quit)

    cfg = ConfigManager()
    seed_test_data_if_needed(cfg)
    use(cfg.config.settings.color_scheme)

    controller = RunnerController(app, cfg)
    app._controller = controller  # keep the controller alive with the app
    controller.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
