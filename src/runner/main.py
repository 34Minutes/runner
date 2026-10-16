"""Main entry point for Runner.

Wires together:
- Config
- Trigger widget (always on top arrow)
- Animated dropdown
- Add/Edit dialog
- Launching
- System tray
- Test data seeding
"""

from __future__ import annotations

import sys
from PySide6.QtCore import Qt, QTimer, QPoint, QSize, QRect
from PySide6.QtGui import QIcon, QAction, QPainter, QPen, QColor, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QMenu,
)

from .config import ConfigManager, Launcher, AppConfig
from .launcher import launch
from .ui.trigger import TriggerWidget
from .ui.dropdown import DropdownPanel
from .ui.add_dialog import AddEditDialog
from .ui.manager_dialog import ManagerDialog
from .ui.stay_on_top import warning as stay_on_top_warning

if sys.platform == "win32":
    from .utils import windows as win_utils  # type: ignore
else:
    win_utils = None  # type: ignore


def seed_test_data_if_needed(cfg: ConfigManager) -> None:
    """Add the requested test data on first run (calc, calendar, web browser)."""
    if cfg.config.launchers:
        return

    if sys.platform == "darwin":
        seeds: list[Launcher] = [
            Launcher.new(name="Calculator", command="Calculator", enabled=True),  # macOS Calculator.app name
            Launcher.new(name="Calendar", command="Calendar", enabled=True),
            Launcher.new(name="Web Browser", command="https://www.google.com", enabled=True),
            Launcher.new(name="TextEdit", command="TextEdit", enabled=True),
            Launcher.new(name="Finder", command="Finder", args="~", enabled=True),
            Launcher.new(name="Terminal", command="Terminal", enabled=True),
        ]
    else:
        seeds: list[Launcher] = [
            Launcher.new(
                name="Calculator",
                command="calc",
                enabled=True,
            ),
            Launcher.new(
                name="Calendar",
                command="ms-calendar:",   # Windows Calendar app via protocol (falls back to browser on other OS)
                enabled=True,
            ),
            Launcher.new(
                name="Web Browser",
                command="https://www.google.com",
                enabled=True,
            ),
            # Practical Windows-friendly examples
            Launcher.new(name="Notepad", command="notepad", enabled=True),
            Launcher.new(name="File Explorer", command="explorer", args=".", enabled=True),
            Launcher.new(name="Command Prompt", command="cmd", enabled=True),
        ]

    for s in seeds:
        cfg.add_launcher(s)


def create_tray(app: QApplication, trigger: TriggerWidget, dropdown: DropdownPanel,
                cfg: ConfigManager) -> QSystemTrayIcon:
    """Create and return a system tray icon with useful menu."""
    tray = QSystemTrayIcon()

    # Draw a crisp small downward arrow for the menu bar / tray.
    # This looks consistent and professional without needing external icon files.
    icon_size = 18
    pix = QPixmap(icon_size, icon_size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor("#0a84ff"), 2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    m = 3
    cx = icon_size // 2
    p.drawLine(m, m + 1, cx, icon_size - m)
    p.drawLine(cx, icon_size - m, icon_size - m, m + 1)
    p.end()
    tray.setIcon(QIcon(pix))

    menu = QMenu()

    act_add = QAction("Add new launcher...", menu)
    act_add.triggered.connect(trigger.request_add.emit)

    act_manage = QAction("Manage launchers...", menu)
    act_manage.triggered.connect(trigger.request_manage.emit)

    act_reset = QAction("Reset position & size", menu)
    act_reset.triggered.connect(trigger.request_reset.emit)

    act_reload = QAction("Reload config", menu)
    def do_reload():
        cfg.reload()
        dropdown.rebuild_buttons(cfg.get_enabled_launchers())
        trigger.update_size_from_settings()
        if cfg.config.settings.pinned_open:
            dropdown.position_adjacent(trigger)
            dropdown.ensure_visible_and_sized()
        # reposition if needed
    act_reload.triggered.connect(do_reload)

    act_exit = QAction("Exit Runner", menu)
    act_exit.triggered.connect(app.quit)

    menu.addAction(act_add)
    menu.addAction(act_manage)
    menu.addAction(act_reset)
    menu.addAction(act_reload)
    menu.addSeparator()
    menu.addAction(act_exit)

    tray.setContextMenu(menu)
    tray.setToolTip("Runner")
    tray.show()

    # Also allow left-click on tray to toggle the list (nice extra)
    def on_tray_activated(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Force show the dropdown near trigger
            dropdown.position_adjacent(trigger)
            dropdown.rebuild_buttons(cfg.get_enabled_launchers())
            if cfg.config.settings.pinned_open:
                dropdown.ensure_visible_and_sized()
            else:
                dropdown.start_show_animation()
            # Ensure arrow stays on top of its list.
            trigger.raise_()
            dropdown.stackUnder(trigger)

    tray.activated.connect(on_tray_activated)

    return tray


def main() -> int:
    app = QApplication(sys.argv)

    # --- Single instance enforcement ---
    # Windows: try a named mutex first (very reliable even across elevation differences).
    if sys.platform == "win32" and win_utils is not None:
        if not win_utils.acquire_single_instance_mutex():
            # Another instance is running — try to wake it via the socket and exit.
            server_name = "Runner_SingleInstance_v1"
            socket = QLocalSocket()
            socket.connectToServer(server_name)
            if socket.waitForConnected(300):
                socket.write(b"show")
                socket.waitForBytesWritten(300)
            socket.close()
            return 0

    # If another copy is running (non-Windows or mutex passed), tell it to show/raise the trigger and exit.
    server_name = "Runner_SingleInstance_v1"
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if socket.waitForConnected(300):
        socket.write(b"show")
        socket.waitForBytesWritten(300)
        socket.close()
        return 0

    # No other instance running — become the server.
    local_server = QLocalServer()
    # Remove any stale socket file (common on macOS after crashes)
    QLocalServer.removeServer(server_name)
    if not local_server.listen(server_name):
        # Fallback: just continue (rare)
        pass

    _trigger_ref = [None]  # mutable holder so handler can see it later

    def _handle_new_connection():
        while local_server.hasPendingConnections():
            client = local_server.nextPendingConnection()
            client.waitForReadyRead(300)
            _ = client.readAll()
            # Any message means "show me"
            trig = _trigger_ref[0]
            if trig is not None:
                trig.show()
                trig.raise_()
                trig.activateWindow()
            client.close()

    local_server.newConnection.connect(_handle_new_connection)

    # Keep server alive
    app._local_server = local_server
    app._trigger_ref = _trigger_ref
    # --- end single instance ---

    # Keep a reference so the handler can always find it (in case of timing)
    # The mutable list above already handles this.

    # Set activation policy as early as possible on macOS.
    # Use integer 1 (Accessory) to avoid enum lookup issues on older system PySide6.
    if sys.platform == "darwin":
        try:
            app.setActivationPolicy(1)  # 1 == ActivationPolicyAccessory
        except Exception:
            pass

    app.setApplicationName("Runner")
    app.setQuitOnLastWindowClosed(False)  # tray + floating widget

    # NOTE: We intentionally do NOT create a hidden QMainWindow here.
    # On macOS, a hidden main window + frameless Tool window + dialogs + activation policy
    # can easily trigger AppKit assertions (EXC_BREAKPOINT / SIGTRAP).
    # The setQuitOnLastWindowClosed(False) + early activation policy is usually sufficient.

    # Support for automated testing: runner --test-quit-after 1500
    test_quit_ms = 0
    if "--test-quit-after" in sys.argv:
        try:
            idx = sys.argv.index("--test-quit-after")
            test_quit_ms = int(sys.argv[idx + 1])
        except Exception:
            test_quit_ms = 1500
        if test_quit_ms > 0:
            QTimer.singleShot(test_quit_ms, app.quit)

    cfg_mgr = ConfigManager()
    seed_test_data_if_needed(cfg_mgr)

    # Create core widgets
    trigger = TriggerWidget(cfg_mgr.config)
    app._trigger_ref[0] = trigger  # for single-instance handler
    dropdown = DropdownPanel(cfg_mgr.config)

    # Initial button population
    dropdown.rebuild_buttons(cfg_mgr.get_enabled_launchers())

    # Validate that saved position is still on screen (e.g. after monitor changes)
    # If not, reset to a safe default.
    def _validate_trigger_position():
        pos = trigger.pos()
        sz = trigger.size()
        on_screen = False
        for screen in QApplication.screens():
            if screen.availableGeometry().intersects(QRect(pos, sz)):
                on_screen = True
                break
        if not on_screen:
            default_w, default_h = 36, 36
            default_x, default_y = 100, 100
            trigger.resize(default_w, default_h)
            trigger.move(default_x, default_y)
            cfg_mgr.update_settings(
                trigger_width=default_w,
                trigger_height=default_h,
                position_x=default_x,
                position_y=default_y,
            )

    _validate_trigger_position()
    dropdown.refresh_filter_visibility()

    # Hover coordination
    # We need to keep the dropdown visible while mouse is in *either* trigger or dropdown.
    # The widgets themselves emit hover_enter / hover_leave.
    # We use a small shared timer + state.

    hide_timer = QTimer()
    hide_timer.setSingleShot(True)
    hide_timer.setInterval(cfg_mgr.config.settings.hover_delay_ms)

    def schedule_hide():
        hide_timer.start()

    def cancel_hide():
        hide_timer.stop()
        dropdown.cancel_hide()  # also cancel dropdown's internal timer to keep list open when mouse is over trigger

    def do_hide():
        if not cfg_mgr.config.settings.pinned_open:
            dropdown.start_hide_animation()

    hide_timer.timeout.connect(do_hide)

    def on_trigger_enter():
        cancel_hide()  # cancels both main timer and dropdown's internal timer
        dropdown.position_adjacent(trigger)
        dropdown.rebuild_buttons(cfg_mgr.get_enabled_launchers())
        if not dropdown.isVisible():
            dropdown.start_show_animation()
        trigger.raise_()
        dropdown.stackUnder(trigger)

    def on_trigger_leave():
        if not cfg_mgr.config.settings.pinned_open:
            schedule_hide()

    def on_dropdown_enter():
        cancel_hide()

    def on_dropdown_leave():
        if not cfg_mgr.config.settings.pinned_open:
            schedule_hide()

    def reset_position_and_size():
        """Reset the trigger to a sensible default location and size."""
        default_w, default_h = 36, 36
        default_x, default_y = 100, 100
        cfg_mgr.update_settings(
            trigger_width=default_w,
            trigger_height=default_h,
            position_x=default_x,
            position_y=default_y,
        )
        trigger.resize(default_w, default_h)
        trigger.move(default_x, default_y)
        trigger.raise_()
        if cfg_mgr.config.settings.pinned_open:
            dropdown.position_adjacent(trigger)
            dropdown.ensure_visible_and_sized()

    trigger.hover_enter.connect(on_trigger_enter)
    trigger.hover_leave.connect(on_trigger_leave)
    dropdown.hover_enter.connect(on_dropdown_enter)
    dropdown.hover_leave.connect(on_dropdown_leave)

    trigger.request_reset.connect(reset_position_and_size)

    # Launch handling
    def on_launch(launcher: Launcher):
        try:
            launch(launcher)
            # Optional: could flash the button or show tray message
            if tray.isVisible():
                tray.showMessage(
                    "Launched", launcher.name, QSystemTrayIcon.MessageIcon.Information, 1200
                )
        except Exception as exc:
            stay_on_top_warning(
                trigger,
                "Launch failed",
                f"Could not launch '{launcher.name}':\n{exc}",
            )
        finally:
            if not cfg_mgr.config.settings.pinned_open:
                # short delay for click visual feedback, then hide (unless pinned)
                QTimer.singleShot(80, dropdown.start_hide_animation)
            else:
                # ensure it stays fully expanded/sized even after click (in case events caused partial state)
                QTimer.singleShot(50, dropdown.ensure_visible_and_sized)
                QTimer.singleShot(55, trigger.raise_)  # re-assert arrow on top after list re-ensure
                QTimer.singleShot(56, lambda: dropdown.stackUnder(trigger))

    dropdown.launch_requested.connect(on_launch)

    # Add dialog wiring
    def show_add_dialog(existing: Launcher | None = None):
        dlg = AddEditDialog(existing, trigger)
        if dlg.exec():
            new_or_updated = dlg.result_launcher
            if new_or_updated:
                if existing:
                    cfg_mgr.update_launcher(new_or_updated)
                else:
                    cfg_mgr.add_launcher(new_or_updated)
                dropdown.rebuild_buttons(cfg_mgr.get_enabled_launchers())

    def apply_pinned_state():
        pinned = cfg_mgr.config.settings.pinned_open
        if pinned:
            dropdown.position_adjacent(trigger)
            dropdown.cancel_hide()
            dropdown.update_height_for_content()
            if not dropdown.isVisible():
                dropdown.start_show_animation()
            else:
                dropdown.update_height_for_content()
            trigger.raise_()
            dropdown.stackUnder(trigger)
        else:
            dropdown.force_hide()

    def show_manager_dialog():
        dlg = ManagerDialog(cfg_mgr, trigger)
        dlg.exec()
        # always rebuild after manager (launchers may have changed) and apply pin state
        dropdown.rebuild_buttons(cfg_mgr.get_enabled_launchers())
        apply_pinned_state()

    trigger.request_add.connect(lambda: show_add_dialog())
    trigger.request_manage.connect(lambda: show_manager_dialog())

    # Connect the quick toggles from the arrow's right-click menu
    def on_pin_toggled(checked):
        cfg_mgr.update_settings(pinned_open=checked)
        apply_pinned_state()

    trigger.pin_toggled.connect(on_pin_toggled)

    def on_filter_toggled(checked):
        cfg_mgr.update_settings(show_filter_box=checked)
        dropdown.refresh_filter_visibility()
        if dropdown.isVisible():
            dropdown.update_height_for_content()
            if cfg_mgr.config.settings.pinned_open:
                dropdown.position_adjacent(trigger)

    trigger.filter_toggled.connect(on_filter_toggled)

    # Windows startup integration
    if sys.platform == "win32" and win_utils is not None:
        # On launch, if the user wants startup, (re)create the Run entry.
        # This makes it resilient if the user moved Runner.exe.
        if cfg_mgr.config.settings.launch_at_startup:
            win_utils.ensure_startup_entry(True)

        def on_startup_toggled(checked):
            cfg_mgr.update_settings(launch_at_startup=checked)
            win_utils.ensure_startup_entry(checked)

        trigger.startup_toggled.connect(on_startup_toggled)

    # Persist position when user drags the trigger
    def save_position(x: int, y: int):
        cfg_mgr.update_settings(position_x=x, position_y=y)
        if cfg_mgr.config.settings.pinned_open:
            dropdown.position_adjacent(trigger)
            dropdown.ensure_visible_and_sized()
            trigger.raise_()
            dropdown.stackUnder(trigger)

    trigger.position_changed.connect(save_position)

    def save_size(w: int, h: int):
        cfg_mgr.update_settings(trigger_width=w, trigger_height=h)
        if cfg_mgr.config.settings.pinned_open:
            dropdown.position_adjacent(trigger)
            dropdown.ensure_visible_and_sized()
            trigger.raise_()
            dropdown.stackUnder(trigger)

    trigger.size_changed.connect(save_size)

    # Exit request from trigger context menu
    trigger.request_exit.connect(app.quit)

    # System tray
    tray = create_tray(app, trigger, dropdown, cfg_mgr)

    # Show the trigger (it starts at saved or default position)
    trigger.show()
    trigger.raise_()

    # Defer initial positioning until after the event loop processes show().
    # Ensures trigger geometry (from persisted size) is realized before dropdown
    # calculates its position relative to it (important for custom sizes + pinned mode).
    QTimer.singleShot(0, apply_pinned_state)

    # On Windows we may want to hide from taskbar / Alt+Tab more aggressively.
    # Qt.Tool + frameless already helps a lot.

    # Run
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
