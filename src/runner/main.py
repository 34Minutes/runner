"""Main entry point for Runner.

Starts Qt, makes sure only one copy runs, loads the config, and hands the
windows to RunnerController.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from . import instance
from .config import ConfigManager, Launcher
from .controller import RunnerController
from .instance import MAX_REQUEST_BYTES, REQUEST_TIMEOUT_MS, SINGLE_INSTANCE_SERVER, _single_instance_name  # noqa: F401
from .ui.theme import use

if sys.platform == "win32":
    from .utils import windows as win_utils  # type: ignore
else:
    win_utils = None  # type: ignore



def _start_in_home_folder() -> None:
    """Work from the home folder, not the folder Runner was started from.

    Windows looks for a bare program name ("notepad") in the current folder
    before PATH. Double-clicking Runner.exe in Downloads makes Downloads the
    current folder, so a downloaded notepad.exe would run in place of the real
    one. Launchers with no working directory also start here.
    """
    try:
        os.chdir(Path.home())
    except OSError:
        pass


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


def _listen_for_other_copies(
    on_show: Callable[[], None],
    on_request: Callable[[object], dict] | None = None,
) -> QLocalServer:
    """Later copies and `runner ctl` connect here.

    A message that starts with "{" is a JSON request for on_request, answered
    on the same connection. Anything else, or nothing, means "show yourself".
    """
    server = QLocalServer()
    # Only this user can connect.
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    # Remove a stale socket file left by a crash (common on macOS).
    QLocalServer.removeServer(SINGLE_INSTANCE_SERVER)
    if not server.listen(SINGLE_INSTANCE_SERVER):
        print(
            f"Runner: single-instance server did not start: {server.errorString()}",
            file=sys.stderr,
        )

    clients: set[_Client] = set()
    server._clients = clients  # each lives until it is answered or hangs up

    def on_new_connection() -> None:
        while server.hasPendingConnections():
            clients.add(_Client(server.nextPendingConnection(), on_show, on_request, clients))

    server.newConnection.connect(on_new_connection)
    return server


class _Client:
    """One connection: a JSON request to answer, or a later copy to show for."""

    def __init__(self, socket: QLocalSocket, on_show, on_request, clients: set) -> None:
        self.socket, self.on_show, self.on_request = socket, on_show, on_request
        self.clients = clients
        self.buffer = bytearray()
        self.done = False
        socket.readyRead.connect(self._read)
        socket.disconnected.connect(self._gone)
        QTimer.singleShot(instance.REQUEST_TIMEOUT_MS, self._time_up)
        self._read()

    def _read(self) -> None:
        if self.done:
            return
        self.buffer += bytes(self.socket.readAll().data())
        if not self.buffer:
            return
        if not self.buffer.lstrip().startswith(b"{"):
            self._show()
            return
        if len(self.buffer) > MAX_REQUEST_BYTES:
            self._answer({"ok": False, "error": "That request is too big."})
        elif b"\n" in self.buffer:
            line = bytes(self.buffer).split(b"\n", 1)[0]
            try:
                request = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                self._answer({"ok": False, "error": f"Not JSON: {exc}"})
                return
            if self.on_request is None:
                self._answer({"ok": False, "error": "Runner is still starting. Try again."})
                return
            try:
                reply = self.on_request(request)
            except Exception as exc:  # noqa: BLE001 - one bad request must not take Runner down
                reply = {"ok": False, "error": f"Runner could not do that: {exc}"}
            self._answer(reply)

    def _answer(self, reply: dict) -> None:
        self.done = True
        self.socket.write(json.dumps(reply, ensure_ascii=False).encode("utf-8") + b"\n")
        self.socket.flush()
        self.socket.disconnectFromServer()

    def _show(self) -> None:
        self.done = True
        self.socket.close()
        self.on_show()

    def _gone(self) -> None:
        # An older copy may write "show" and hang up before it is read.
        try:
            if not self.done:
                self.buffer += bytes(self.socket.readAll().data())
                if not self.buffer.lstrip().startswith(b"{"):
                    self._show()
                self.done = True
            self.socket.deleteLater()
        except RuntimeError:  # Qt already deleted the socket, at shutdown
            self.done = True
        self.clients.discard(self)

    def _time_up(self) -> None:
        if not self.done:
            self.done = True
            self.socket.abort()
        self.clients.discard(self)


def _test_quit_ms(argv: list[str]) -> int:
    """`runner --test-quit-after 1500` quits on its own, for automated runs."""
    if "--test-quit-after" not in argv:
        return 0
    try:
        return int(argv[argv.index("--test-quit-after") + 1])
    except (IndexError, ValueError):
        return 1500


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "ctl":
        from .ctl import main as ctl_main

        return ctl_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "project":
        from .project_cli import main as project_main

        return project_main(sys.argv[2:])
    _start_in_home_folder()
    app = QApplication(sys.argv)

    if sys.platform == "win32" and win_utils is not None:
        # The session mutex decides. Named pipes are shared by every user on
        # the machine, so a pipe answering is no proof that this user's
        # Runner is running.
        if not win_utils.acquire_single_instance_mutex():
            _signal_running_copy()
            return 0
    elif _signal_running_copy():
        return 0

    controller: RunnerController | None = None

    def show_running_copy() -> None:
        if controller is not None:
            controller.bring_forward()

    def answer_request(request: object) -> dict:
        if controller is None:
            return {"ok": False, "error": "Runner is still starting. Try again."}
        return controller.answer_outside_request(request)

    server = _listen_for_other_copies(show_running_copy, answer_request)
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
